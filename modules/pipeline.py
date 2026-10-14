from __future__ import annotations

import re
from time import perf_counter

from modules.conversation_state import update_state_from_result
from modules.llm_client import LLMGateway
from modules.metrics import record_pipeline_metric
from modules.models import (
    Certainty,
    ConversationState,
    DialogueStage,
    PipelineResult,
    SafetySignal,
    SafetyStatus,
    UserIntent,
)
from modules.response_generator import generate_candidate
from modules.response_guard import guard_response
from modules.response_planner import plan_turn
from modules.risk_router import precheck_safety
from modules.stage_controller import choose_stage
from modules.state_analyzer import analyze_turn, offline_analysis
from utils.text_utils import clean_text, truncate_text


class UserInputError(ValueError):
    pass


_QUOTED_SPAN_PATTERNS = [
    re.compile(r"“[^”]*”"),
    re.compile(r"‘[^’]*’"),
    re.compile(r'"[^"]*"'),
    re.compile(r"'[^']*'"),
    re.compile(r"`[^`]*`"),
]
_CURRENT_SELF_HARM_PATTERN = re.compile(
    r"(?:^|[，,。；;！？!?\n])\s*"
    r"(?:但|不过|可是|而且|同时|另外|然后)?\s*"
    r"我(?P<context>.{0,28}?)"
    r"(?P<signal>"
    r"不想活|想死|想自杀|"
    r"有(?:伤害自己|结束生命|自杀|自伤)的想法|"
    r"想伤害自己|有自伤想法|"
    r"不能保证(?:自己)?安全|控制不住自己"
    r")"
)
_CURRENT_OTHER_HARM_PATTERN = re.compile(
    r"(?:^|[，,。；;！？!?\n])\s*"
    r"(?:但|不过|可是|而且|同时|另外|然后)?\s*"
    r"我(?P<context>.{0,24}?)"
    r"(?P<signal>"
    r"(?:想|要|准备)?让(?:他|她)去死|"
    r"(?:想|要|准备)杀(?:了)?(?:他|她|对方)|"
    r"(?:想|要|准备)伤害(?:他|她|别人|对方)|"
    r"有伤害(?:他|她|别人|对方)的打算"
    r")"
)
_NEGATED_CURRENT_CONTEXT = re.compile(
    r"(?:并不|并非|没有|不会|不是|不|没|并).{0,4}$"
)
_REPORTING_CONTEXT_MARKERS = ("引用", "复述", "研究", "讨论", "台词", "写着", "原话", "例句", "说")
_CURRENT_CONTEXT_MARKERS = ("现在", "目前", "此刻", "突然", "真的", "确实", "自己", "也", "已经", "马上")
_SAFETY_ROUTE_STATUSES = {SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4}
_SAFETY_RESPONSE_HISTORY_MARKERS = (
    "安全关键点",
    "伤害自己或结束生命的想法",
    "风险主体是你提到的那个人",
    "现实人员已经接上",
    "继续按 S3",
    "保持 S3",
    "拨打 110",
    "拨打 120",
    "110/120",
    "12356",
    "伤害对方的打算",
    "只是气头上的表达",
    "明确告知存在他伤风险",
    "对方当前相关想法仍在",
    "能否保证接下来一小时不伤害自己",
)


def _state_for_new_turn(state: ConversationState) -> ConversationState:
    """Return a working copy without carrying transient labels as hard facts.

    Understanding feedback updates the completed turn immediately, so the user
    can inspect the corrected sidebar state. Emotion, support intent, advice
    readiness, and inferred needs are turn-scoped, however: on the next message
    they remain available through ``last_analysis`` but must be inferred again
    rather than overriding new evidence. The confirmed main issue is retained as
    a cautious fallback for genuinely underspecified follow-up messages.
    """

    updated = state.model_copy(deep=True)
    updated.confirmed_primary_emotion = None
    updated.confirmed_secondary_emotions = []
    updated.confirmed_intent = None
    updated.confirmed_advice_readiness = None
    updated.confirmed_needs = []
    return updated


def _without_quoted_spans(text: str) -> str:
    result = text
    for pattern in _QUOTED_SPAN_PATTERNS:
        result = pattern.sub("", result)
    return result


def _explicit_current_harm_statement(text: str, pattern: re.Pattern[str]) -> str | None:
    """Extract a conservative first-person current-harm statement outside quotes."""

    unquoted = _without_quoted_spans(text)
    for match in pattern.finditer(unquoted):
        context = match.group("context")
        if _NEGATED_CURRENT_CONTEXT.search(context):
            continue

        latest_reporting = max(
            (context.rfind(marker) for marker in _REPORTING_CONTEXT_MARKERS),
            default=-1,
        )
        latest_current = max(
            (context.rfind(marker) for marker in _CURRENT_CONTEXT_MARKERS),
            default=-1,
        )
        if latest_reporting >= 0 and latest_current <= latest_reporting:
            continue

        # Rebuild a minimal statement so discussion or attribution words in the
        # surrounding clause cannot mask the current first-person signal.
        return f"我现在{match.group('signal')}"
    return None


def _mixed_context_safety_override(
    user_input: str,
    existing: SafetySignal,
) -> SafetySignal | None:
    """Prefer an explicit current first-person harm statement over attribution."""

    for pattern in (_CURRENT_SELF_HARM_PATTERN, _CURRENT_OTHER_HARM_PATTERN):
        statement = _explicit_current_harm_statement(user_input, pattern)
        if not statement:
            continue
        candidate = precheck_safety(statement)
        if candidate.status not in _SAFETY_ROUTE_STATUSES:
            continue

        candidate_severity = int(candidate.status.value[1])
        existing_severity = int(existing.status.value[1])
        if candidate_severity > existing_severity or (
            candidate_severity == existing_severity and existing.subject != "本人"
        ):
            return candidate
    return None


def _history_marks_safety_episode(history: list[dict]) -> bool:
    """Detect a safety episode even when the limited window starts mid-turn."""

    for message in history:
        meta = message.get("meta")
        if isinstance(meta, dict) and meta.get("stage") == DialogueStage.SAFETY.value:
            return True
        if str(message.get("role", "")) != "assistant":
            continue
        content = clean_text(str(message.get("content", "")))
        if any(marker in content for marker in _SAFETY_RESPONSE_HISTORY_MARKERS):
            return True
    return False


def _provider_history_without_safety_episodes(
    history: list[dict],
    *,
    active_safety: bool,
) -> list[dict[str, str]]:
    """Exclude safety episodes from any later third-party provider payload."""

    # A bounded history window may start after the first safety disclosure. A
    # fixed safety response or retained stage metadata therefore causes the
    # whole limited window to be withheld rather than risking a partial leak.
    if active_safety or _history_marks_safety_episode(history):
        return []

    filtered: list[dict[str, str]] = []
    previous_signal: SafetySignal | None = None
    episode_active = False
    suppress_current_turn = False

    for message in history:
        role = str(message.get("role", ""))
        content = clean_text(str(message.get("content", "")))
        if role == "user":
            signal = precheck_safety(content, previous_signal)
            suppress_current_turn = episode_active or signal.status in _SAFETY_ROUTE_STATUSES
            if signal.status in _SAFETY_ROUTE_STATUSES:
                episode_active = True
            elif episode_active and signal.status == SafetyStatus.S0:
                episode_active = False
            previous_signal = signal
            if not suppress_current_turn:
                filtered.append({"role": role, "content": content})
        elif role == "assistant" and not suppress_current_turn:
            filtered.append({"role": role, "content": content})

    return filtered


def _local_analysis_for_forced_safety(
    user_input: str,
    full_safety: SafetySignal,
    state: ConversationState,
    selected_mode: str | None,
    *,
    full_input_scan: bool,
    mixed_context_override: bool,
):
    """Build a controlled local analysis when ordinary analysis is bypassed."""

    analysis = offline_analysis(user_input, state, selected_mode)
    analysis.safety = full_safety
    analysis.suggested_stage = DialogueStage.SAFETY
    analysis.user_intent = UserIntent.SAFETY
    analysis.certainty = Certainty.HIGH
    if full_safety.status in {SafetyStatus.S3, SafetyStatus.S4}:
        analysis.emotion_intensity = 5
    elif full_safety.status == SafetyStatus.S2:
        analysis.emotion_intensity = max(analysis.emotion_intensity, 4)
    analysis.underlying_needs = list(
        dict.fromkeys(
            [
                "当前安全",
                "现实陪伴",
                "专业或紧急支持",
                *analysis.underlying_needs,
            ]
        )
    )[:5]
    if full_input_scan:
        analysis.input_features["full_input_safety_scan"] = True
    if mixed_context_override:
        analysis.input_features["mixed_context_safety_override"] = True
    return analysis


def process_message(
    raw_input: str,
    history: list[dict],
    state: ConversationState,
    selected_mode: str | None = None,
    selected_strategy_mode: str | None = None,
    llm_gateway: LLMGateway | None = None,
) -> PipelineResult:
    started = perf_counter()
    cleaned_input = clean_text(raw_input)
    if not cleaned_input:
        raise UserInputError("请输入内容后再发送。")

    turn_state = _state_for_new_turn(state)
    previous_safety = (
        turn_state.last_analysis.safety if turn_state.last_analysis else None
    )
    full_input_safety = precheck_safety(cleaned_input, previous_safety)
    mixed_override = _mixed_context_safety_override(
        cleaned_input,
        full_input_safety,
    )
    if mixed_override is not None:
        full_input_safety = mixed_override

    # Keep both the scan's input and execution order ahead of truncation.
    user_input = truncate_text(cleaned_input)
    full_input_scan = cleaned_input != user_input
    current_safety_route = full_input_safety.status in _SAFETY_ROUTE_STATUSES
    provider_history = _provider_history_without_safety_episodes(
        history,
        active_safety=(
            previous_safety is not None
            and previous_safety.status in _SAFETY_ROUTE_STATUSES
        ),
    )

    # S2-S4 turns stay local. The full cleaned input is scanned before ordinary
    # truncation, and explicit current harm can override surrounding discussion
    # or third-party attribution. Safety episodes are also removed from future
    # provider history so a locally handled turn cannot leak on a later request.
    if current_safety_route:
        analysis = _local_analysis_for_forced_safety(
            user_input,
            full_input_safety,
            turn_state,
            selected_mode,
            full_input_scan=full_input_scan,
            mixed_context_override=mixed_override is not None,
        )
        analysis_fallback = True
        analysis_error = "local_safety_protocol"
    else:
        analysis, analysis_fallback, analysis_error = analyze_turn(
            user_input, provider_history, turn_state, selected_mode, llm_gateway
        )

    stage = choose_stage(analysis, turn_state, selected_mode, user_input)
    plan = plan_turn(
        analysis,
        turn_state,
        stage,
        history=history,
        user_input=user_input,
        selector_mode=selected_strategy_mode,
    )
    # A referenced option must be resolved before Act. The planner may ask a
    # local clarification; all safety routing above remains authoritative.
    stage = plan.stage
    candidate, fallback, generation_fallback, generation_error = generate_candidate(
        user_input, provider_history, analysis, turn_state, plan, llm_gateway
    )
    final_generated, audit, guard_fallback, guard_error = guard_response(
        candidate,
        fallback,
        analysis,
        plan,
        None if (plan.selected_option or plan.choice_clarification) else llm_gateway,
        user_input=user_input,
    )

    raw_error_code = analysis_error or generation_error or guard_error
    if raw_error_code == "local_safety_protocol":
        mode = "安全模式"
        provider_used = "local_safety"
        model_used = "固定安全协议"
    elif llm_gateway is None:
        mode = "演示模式"
        provider_used = "offline"
        model_used = "离线规则"
    else:
        mode = "在线模式"
        provider_used = llm_gateway.config.provider.value
        model_used = llm_gateway.config.model

    # Offline demonstration and the controlled safety route are intentional
    # execution modes, not degraded provider fallbacks. Preserve fallback status
    # for ordinary online turns that had to leave the configured model path.
    unexpected_fallback = (
        llm_gateway is not None
        and stage != DialogueStage.SAFETY
        and (analysis_fallback or generation_fallback or guard_fallback)
    )
    expected_local_status = (
        llm_gateway is None and raw_error_code == "missing_api_key"
    ) or (
        stage == DialogueStage.SAFETY
        and raw_error_code == "local_safety_protocol"
    )
    error_code = None if expected_local_status else raw_error_code

    provisional = PipelineResult(
        response=final_generated.response,
        analysis=analysis,
        plan=plan,
        audit=audit,
        state=turn_state,
        used_fallback=unexpected_fallback,
        mode=mode,
        provider_used=provider_used,
        model_used=model_used,
        error_code=error_code,
        latency_ms=int((perf_counter() - started) * 1000),
    )

    # Selection is owned by the Guard; its fallback flag is status metadata,
    # not a recipe for reconstructing a response/card pair.
    provisional.state = update_state_from_result(
        turn_state, provisional, final_generated.action_plan
    )
    record_pipeline_metric(provisional)
    return provisional
