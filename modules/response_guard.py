from __future__ import annotations

import json
import re

from config import GUARD_MAX_TOKENS, GUARD_TEMPERATURE, PROMPT_DIR
from modules.llm_client import LLMGateway, LLMServiceError, call_json, is_llm_configured
from modules.models import (
    ActionPlan,
    DialogueStage,
    GeneratedResponse,
    GuardResult,
    ResponseAudit,
    TurnAnalysis,
    TurnPlan,
)
from utils.text_utils import count_questions, normalize_for_rules, visible_char_count


DIAGNOSIS_PHRASES = [
    "你就是抑郁症",
    "你一定是抑郁症",
    "你有抑郁倾向",
    "你这是心理疾病",
]
COERCIVE_PHRASES = ["你必须", "你应该立刻", "照我说的做", "不要告诉任何人", "不用找别人"]
ADVICE_PHRASES = ["建议你", "你应该", "不妨", "你可以试试", "最好"]
UNSUPPORTED_CERTAINTY_PHRASES = ["你肯定是", "你一定是", "显然是", "就是因为", "原因就是"]
SENSITIVE_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{12,}",
    r"\b(?:[A-Z0-9_]+_)?API[_ -]?KEY\b[\"']?\s*[:=：]",
    r"系统提示(?:词(?:全文|原文)?|全文|原文)(?:如下|是|为)",
    r"\b(?:system|developer)[ _](?:prompt|message)[\"']?\s*(?:is\b|[:=：])",
    r"\b(?:system_prompt|developer_prompt|base_url|llm_config)[\"']?\s*[:=：]",
    r"内部配置(?:如下|是|为)",
]
ACTION_PLAN_TEXT_FIELDS = (
    "action", "when", "location", "success_criterion", "obstacle", "fallback",
    "review_prompt", "status",
)
CONTENT_VIOLATIONS = {
    "diagnosis": "出现医学诊断或标签化判断",
    "coercion": "出现强迫、隔离现实支持或命令式措辞",
    "assumption": "把未经确认的解释写成确定事实",
    "sensitive_leak": "疑似泄露密钥、系统提示或内部配置",
}


class GuardResponseError(RuntimeError):
    """Neither the candidate nor the required fallback is safe to return."""


def _outside_quotes(text: str) -> str:
    result = text
    for pattern in [r"“[^”]*”", r"‘[^’]*’", r'"[^"]*"', r"'[^']*'", r"`[^`]*`"]:
        result = re.sub(pattern, "", result)
    return result


def _content_flags(text: str, *, check_quoted_assumptions: bool = False) -> dict[str, bool]:
    assumption_text = text if check_quoted_assumptions else _outside_quotes(text)
    return {
        "diagnosis": any(phrase in text for phrase in DIAGNOSIS_PHRASES),
        "coercion": any(phrase in text for phrase in COERCIVE_PHRASES),
        "assumption": any(phrase in assumption_text for phrase in UNSUPPORTED_CERTAINTY_PHRASES),
        "sensitive_leak": any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in SENSITIVE_PATTERNS),
    }


def _action_plan_findings(action_plan: ActionPlan | None) -> list[tuple[str, str]]:
    findings = []
    if action_plan is not None:
        for field in ACTION_PLAN_TEXT_FIELDS:
            # Card strings may be rendered or downloaded verbatim, including
            # their quoted contents. Record only field names and categories.
            flags = _content_flags(getattr(action_plan, field), check_quoted_assumptions=True)
            findings.extend((field, kind) for kind, failed in flags.items() if failed)
    return findings


def _action_plan_consistent(response: str, action_plan: ActionPlan) -> bool:
    normalized_response = normalize_for_rules(response)
    normalized_action = normalize_for_rules(action_plan.action)
    if not normalized_action:
        return False

    # The response may add connective wording, but it must preserve a useful
    # anchor from the structured action rather than describing a different task.
    anchor_length = min(12, max(6, len(normalized_action)))
    action_anchor = normalized_action[:anchor_length]
    action_present = action_anchor in normalized_response

    minutes = str(action_plan.duration_minutes)
    duration_present = any(
        normalize_for_rules(marker) in normalized_response
        for marker in [f"{minutes}分钟", f"{minutes} 分钟", f"{minutes}min"]
    )
    return action_present and duration_present


def deterministic_audit(
    response: str,
    analysis: TurnAnalysis,
    plan: TurnPlan,
    action_plan: ActionPlan | None = None,
    *,
    validate_action_plan: bool = False,
) -> ResponseAudit:
    violations = []
    questions = count_questions(response)
    char_count = visible_char_count(response)
    unquoted = _outside_quotes(response)
    empty_response = not response.strip()
    content_flags = _content_flags(response)
    card_findings = _action_plan_findings(action_plan)
    premature = not plan.advice_allowed and any(word in unquoted for word in ADVICE_PHRASES)
    unsupported_assumption = content_flags["assumption"] or any(
        kind == "assumption" for _, kind in card_findings
    )

    if empty_response:
        violations.append("回复为空")
    if questions > plan.max_questions:
        violations.append("主要问题超过一个")
    for kind, failed in content_flags.items():
        if failed:
            violations.append(CONTENT_VIOLATIONS[kind])
    for field, kind in card_findings:
        violations.append(f"行动卡 {field}：{CONTENT_VIOLATIONS[kind]}")
    if premature:
        violations.append("在建议许可门之前给出建议")

    correction_missing = False
    if analysis.correction:
        confirmed_tokens = [
            token
            for token in re.split(r"[/；、,，]", analysis.correction.confirmed_value)
            if token
        ]
        correction_missing = bool(confirmed_tokens) and not any(
            token in response or (len(token) > 6 and token[:6] in response)
            for token in confirmed_tokens
        )
        if correction_missing:
            violations.append("没有采用用户明确纠正后的确认值")

    action_stage_mismatch = False
    action_inconsistent = False
    if validate_action_plan:
        if plan.stage == DialogueStage.ACT:
            if action_plan is None:
                action_stage_mismatch = True
                violations.append("行动阶段缺少结构化行动卡")
            elif not _action_plan_consistent(response, action_plan):
                action_inconsistent = True
                violations.append("回复正文与结构化行动卡不一致")
        elif action_plan is not None:
            action_stage_mismatch = True
            violations.append("非行动阶段不应返回结构化行动卡")

    safety_protocol_missing = False
    if analysis.safety.status.value == "S4":
        safety_protocol_missing = not (
            ("110" in response or "120" in response)
            and any(
                marker in response
                for marker in ["身边有人", "到场", "前台", "楼道", "公共", "不独处"]
            )
        )
        if safety_protocol_missing:
            violations.append("S4 回复缺少现实紧急服务或结束独处指令")

    length_passed = plan.min_chars <= char_count <= plan.max_chars
    if not length_passed:
        violations.append(f"长度 {char_count} 不在 {plan.min_chars}-{plan.max_chars} 范围")

    hard_safety_failure = (
        empty_response
        or any(content_flags.values())
        or bool(card_findings)
        or safety_protocol_missing
    )
    stage_adherence = not (
        correction_missing or action_stage_mismatch or action_inconsistent
    )
    return ResponseAudit(
        stage_adherence=stage_adherence,
        emotion_validation=True,
        premature_advice=premature,
        unsupported_assumption=unsupported_assumption,
        question_count=questions,
        autonomy_respected=not (
            content_flags["coercion"] or any(kind == "coercion" for _, kind in card_findings)
        ),
        safety_passed=not hard_safety_failure,
        length_passed=length_passed,
        violations=violations,
    )


def _guard_messages(
    candidate: GeneratedResponse,
    analysis: TurnAnalysis,
    plan: TurnPlan,
    user_input: str,
) -> list[dict[str, str]]:
    template = (PROMPT_DIR / "guard_prompt.txt").read_text(encoding="utf-8")
    schema = json.dumps(GuardResult.model_json_schema(), ensure_ascii=False)
    payload = {
        "current_input": user_input,
        "candidate_response": candidate.response,
        "candidate_action_plan": (
            candidate.action_plan.model_dump(mode="json")
            if candidate.action_plan is not None
            else None
        ),
        "analysis": analysis.model_dump(mode="json"),
        "turn_plan": plan.model_dump(mode="json"),
    }
    return [
        {"role": "system", "content": template.replace("{schema}", schema)},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _hard_failure(audit: ResponseAudit, plan: TurnPlan) -> bool:
    # Length alone remains soft; empty text is a separate safety failure.
    return (
        not audit.safety_passed
        or audit.premature_advice
        or audit.unsupported_assumption
        or audit.question_count > plan.max_questions
        or not audit.stage_adherence
    )


def guard_response(
    candidate: GeneratedResponse,
    fallback: GeneratedResponse,
    analysis: TurnAnalysis,
    plan: TurnPlan,
    gateway: LLMGateway | None = None,
    *,
    user_input: str = "",
) -> tuple[GeneratedResponse, ResponseAudit, bool, str | None]:
    """Select the complete response/card pair without losing current-input context."""
    def audit_generated(generated: GeneratedResponse) -> ResponseAudit:
        return deterministic_audit(
            generated.response, analysis, plan, generated.action_plan,
            validate_action_plan=True,
        )

    def select_fallback(error: str | None) -> tuple[GeneratedResponse, ResponseAudit, bool, str | None]:
        selected = fallback.model_copy(deep=True)
        audit = audit_generated(selected)
        if _hard_failure(audit, plan):
            # Fallbacks may contain user-derived fields. Never echo unsafe
            # content in the exception; the existing UI handles fixed errors.
            raise GuardResponseError("guard_no_safe_response")
        return selected, audit, True, error

    # A text-only repair cannot make an unsafe card safe. Intercept before
    # sending the card to an online Guard; empty candidates also stay local.
    if not candidate.response.strip() or _action_plan_findings(candidate.action_plan):
        return select_fallback(None)

    selected = candidate.model_copy(deep=True)
    error_code = None

    if is_llm_configured(gateway) and plan.stage != DialogueStage.SAFETY:
        try:
            data = call_json(
                gateway=gateway,
                messages=_guard_messages(candidate, analysis, plan, user_input),
                temperature=GUARD_TEMPERATURE,
                max_tokens=GUARD_MAX_TOKENS,
            )
            guarded = GuardResult.model_validate(data)
            selected = candidate.model_copy(
                update={"response": guarded.final_response.strip()}, deep=True
            )
        except Exception as exc:
            error_code = exc.code if isinstance(exc, LLMServiceError) else "guard_invalid"

    final_audit = audit_generated(selected)
    if _hard_failure(final_audit, plan):
        return select_fallback(error_code)

    # A successful model-assisted repair keeps the candidate action plan and is
    # not the same event as selecting the controlled fallback response.
    return selected, final_audit, False, error_code
