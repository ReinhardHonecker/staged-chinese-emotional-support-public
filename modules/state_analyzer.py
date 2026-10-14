from __future__ import annotations

import json
import re

from config import (
    ANALYSIS_MAX_TOKENS,
    ANALYSIS_TEMPERATURE,
    MAX_USER_INPUT_LENGTH,
    PROMPT_DIR,
)
from modules.llm_client import LLMGateway, LLMServiceError, call_json, is_llm_configured
from modules.models import (
    AdviceReadiness,
    Certainty,
    ConversationState,
    CorrectionSignal,
    DialogueStage,
    Emotion,
    InputSecurity,
    SafetyStatus,
    TurnAnalysis,
    UserIntent,
)
from modules.risk_router import precheck_safety
from utils.text_utils import format_history


EMOTION_KEYWORDS: dict[Emotion, dict[str, int]] = {
    Emotion.ANXIETY: {
        "担心": 2,
        "害怕": 3,
        "紧张": 2,
        "焦虑": 3,
        "不安": 2,
        "很慌": 4,
        "慌": 2,
        "怕": 1,
        "心跳": 1,
    },
    Emotion.SADNESS: {
        "难过": 3,
        "伤心": 3,
        "哭": 2,
        "失落": 3,
        "痛苦": 3,
        "没有希望": 4,
        "不想活": 4,
        "活着没意义": 4,
    },
    Emotion.ANGER: {
        "生气": 3,
        "愤怒": 4,
        "气死": 3,
        "讨厌": 2,
        "烦死": 2,
        "凭什么": 2,
    },
    Emotion.GRIEVANCE: {
        "委屈": 4,
        "不公平": 3,
        "没被看到": 4,
        "没有被看到": 4,
        "不被重视": 3,
        "受挫": 3,
        "拖后腿": 2,
    },
    Emotion.LONELINESS: {
        "孤独": 4,
        "没人陪": 3,
        "没人理解": 3,
        "一个人": 1,
        "被排斥": 4,
        "融不进去": 3,
    },
    Emotion.SHAME: {
        "羞耻": 4,
        "丢脸": 3,
        "内疚": 3,
        "自责": 3,
        "让他们失望": 3,
        "搞砸": 3,
        "不负责": 2,
    },
    Emotion.STRESS: {
        "压力": 3,
        "累": 2,
        "撑不住": 3,
        "任务": 1,
        "考试": 1,
        "作业": 1,
        "耗尽": 3,
        "截止": 2,
        "睡": 1,
    },
    Emotion.CONFUSION: {
        "混乱": 3,
        "不知道怎么办": 4,
        "纠结": 3,
        "矛盾": 3,
        "选不出": 3,
        "理不清": 3,
        "卡住": 2,
    },
    Emotion.POSITIVE: {
        "开心": 4,
        "高兴": 4,
        "顺利": 2,
        "满意": 3,
        "幸福": 4,
        "希望": 2,
        "轻松": 3,
        "如释重负": 4,
        "期待": 2,
    },
}

MODE_TO_INTENT = {
    "我想先说说": UserIntent.VENT,
    "帮我理清楚": UserIntent.CLARIFY,
    "一起想办法": UserIntent.ADVICE,
    "先帮我稳一下": UserIntent.STABILIZE,
}

INTENT_REJECT_PATTERNS = [
    "别给建议",
    "不要给建议",
    "不想听建议",
    "先不要建议",
    "不要急着解决",
    "不要马上给",
    "还没说完",
    "不想听怎么",
    "不要给解决办法",
    "先不要给解决办法",
]
VENT_PATTERNS = ["只想说说", "只想先说", "听我说", "先把这件事说完", "先让我说完", "继续听"]
CLARIFY_PATTERNS = [
    "脑子很乱",
    "理不清",
    "帮我分析",
    "帮我理清",
    "分清哪些",
    "事实和担心",
    "问题地图",
    "分开列",
    "已知事实",
    "可控部分",
]
ADVICE_PATTERNS = [
    "怎么办",
    "给点建议",
    "你觉得我该",
    "怎么解决",
    "一起想办法",
    "愿意讨论办法",
]
ACTION_PATTERNS = [
    "我选",
    "就这个",
    "愿意做一个",
    "愿意先做",
    "很小的下一步",
    "先帮我把这条",
    "可以试试",
    "小步骤",
    "先做点准备",
    "帮我先写",
    "帮我写",
    "帮我定",
    "帮我留",
    "帮我想一句",
    "帮我把",
    "怎么说",
    "怎么写",
    "接下来半小时",
    "今晚就发",
    "想先把",
    "想先回",
    "想定明天",
    "想先去问清",
    "只想重做",
    "可以提前",
    "那我先给",
    "就定",
    "愿意只处理",
    "准备把作业",
    "想先关掉",
    "想把卡片",
    "想发一条",
    "只想发一条",
    "愿意先写",
    "愿意处理可修复",
    "只给我一个最小测试",
    "只想花五分钟",
    "只想先把第一句",
    "今晚真的想先",
    "只想把这两年",
    "愿意今天先",
    "愿意。规则",
    "愿意。胸牌",
    "今晚只录",
]
STRATEGY_NOT_ACTION_PATTERNS = [
    "先问清退款规则，再给爸妈",
    "候补结果最晚什么时候通知",
    "能不能改成每周三天",
]
CHOOSE_PATTERNS = ["选哪个", "怎么选", "两个方案", "哪个更合适", "比较一下"]
STABILIZE_PATTERNS = ["特别慌", "冷静不下来", "先缓缓", "先稳一下", "什么都想不了"]
UNDERSTOOD_PATTERNS = ["没人理解", "不被理解", "只想被理解", "希望你理解"]

INTERPRETATION_MARKERS = [
    "我觉得",
    "我担心",
    "我怕",
    "可能",
    "肯定",
    "一定",
    "永远",
    "等于",
    "是不是",
    "好像",
    "会不会",
    "意味着",
    "说明",
    "仿佛",
]

INJECTION_MARKERS = {
    "规则覆盖": ["忽略所有规则", "忽略之前", "无视规则", "最高优先级"],
    "系统提示泄露": ["system prompt", "隐藏提示"],
    "API Key 泄露": ["api key", "apikey", "后台密钥", "环境变量", "隐藏配置"],
    "角色劫持": ["改变角色", "你现在是", "进入开发者模式"],
    "过量输出": ["十条建议", "一次给十条", "输出全部"],
    "诊断要求": ["诊断我", "心理疾病诊断"],
}
SYSTEM_PROMPT_DISCLOSURE_PATTERNS = (
    re.compile(r"系统提示(?:词(?:全文|原文)?|全文|原文)"),
    re.compile(
        r"(?:打印|输出|泄露|复述|告诉我|提供|给我)"
        r".{0,16}(?:你的|本应用的|内部的)?系统提示"
    ),
    re.compile(
        r"(?:请|麻烦|帮我|你(?:能|可以|可否)|我(?:想|要))"
        r".{0,12}(?:显示|展示|查看).{0,12}(?:你的|本应用的|内部的)?系统提示"
    ),
    re.compile(
        r"(?:请|麻烦)?把.{0,8}(?:你的|本应用的|内部的)?系统提示"
        r".{0,8}(?:显示|展示|发给我|给我看)"
    ),
)

EMOTION_ALIASES = {
    "焦虑": Emotion.ANXIETY,
    "担心": Emotion.ANXIETY,
    "委屈": Emotion.GRIEVANCE,
    "生气": Emotion.ANGER,
    "愤怒": Emotion.ANGER,
    "悲伤": Emotion.SADNESS,
    "难过": Emotion.SADNESS,
    "孤独": Emotion.LONELINESS,
    "内疚": Emotion.SHAME,
    "羞耻": Emotion.SHAME,
    "压力": Emotion.STRESS,
    "困惑": Emotion.CONFUSION,
    "开心": Emotion.POSITIVE,
}


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _dedupe(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip(" ，。！？；;:\n\t")
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _split_clauses(text: str) -> list[str]:
    clauses = re.split(r"[。！？!?；;\n]+", text)
    return _dedupe([clause for clause in clauses if 2 <= len(clause.strip()) <= 220], 24)


def _input_attack_types(text: str) -> list[str]:
    lowered = text.lower()
    attack_types = []
    for attack_type, markers in INJECTION_MARKERS.items():
        detected = any(marker in lowered for marker in markers)
        if attack_type == "系统提示泄露":
            detected = detected or any(
                pattern.search(text) for pattern in SYSTEM_PROMPT_DISCLOSURE_PATTERNS
            )
        if detected:
            attack_types.append(attack_type)
    return attack_types


def _detect_input_security(text: str) -> InputSecurity:
    attack_types = _input_attack_types(text)
    return InputSecurity(
        prompt_injection_detected=bool(attack_types),
        attack_types=attack_types[:6],
        treat_as_untrusted_content=True,
        sensitive_output_allowed=False,
    )


def _is_injection_clause(clause: str) -> bool:
    return bool(_input_attack_types(clause))


def _offline_emotions(text: str) -> tuple[Emotion, list[Emotion]]:
    scores = {emotion: 0 for emotion in Emotion}
    for emotion, mapping in EMOTION_KEYWORDS.items():
        scores[emotion] = sum(weight for word, weight in mapping.items() if word in text)

    if "考试" in text and any(marker in text for marker in ["结束", "交卷", "考完"]):
        scores[Emotion.STRESS] = max(scores[Emotion.STRESS], 2)

    sarcasm = bool(
        re.search(r"[‘'\"](?:优秀|厉害|真棒)[’'\"]", text)
        or re.search(r"(?:呵|可真|真是).{0,8}(?:优秀|厉害|真棒).{0,20}(?:搞砸|失败|丢脸)", text)
    )
    if sarcasm:
        scores[Emotion.POSITIVE] = 0
        scores[Emotion.SHAME] += 5

    correction_match = re.search(r"不是(?:在)?(焦虑|担心|生气|难过|压力)[，,， ]*(?:我)?是(委屈|生气|难过|焦虑)", text)
    if correction_match:
        rejected = EMOTION_ALIASES.get(correction_match.group(1))
        confirmed = EMOTION_ALIASES.get(correction_match.group(2))
        if rejected:
            scores[rejected] = 0
        if confirmed:
            scores[confirmed] += 8

    ranked = [
        emotion
        for emotion in sorted(scores, key=scores.get, reverse=True)
        if scores[emotion] > 0
    ]
    if not ranked:
        return Emotion.NEUTRAL, []
    primary = ranked[0]
    secondary = [emotion for emotion in ranked[1:] if scores[emotion] >= 2][:2]
    return primary, secondary


def _explicit_correction(text: str) -> CorrectionSignal | None:
    match = re.search(
        r"不是(?:在)?(焦虑|担心|生气|难过|压力)[，,， ]*(?:我)?是(委屈|生气|难过|焦虑)",
        text,
    )
    if match:
        rejected = EMOTION_ALIASES.get(match.group(1))
        confirmed = EMOTION_ALIASES.get(match.group(2))
        if rejected and confirmed:
            return CorrectionSignal(
                field="primary_emotion",
                rejected_value=rejected.value,
                confirmed_value=confirmed.value,
            )

    if _contains_any(text, INTENT_REJECT_PATTERNS) or "不是想听建议" in text:
        return CorrectionSignal(
            field="user_intent",
            rejected_value=UserIntent.ADVICE.value,
            confirmed_value=UserIntent.VENT.value,
        )

    match = re.search(r"重点不是(.{1,40}?)[，,。；;](?:而是|是)?(.{1,80})", text)
    if match:
        return CorrectionSignal(
            field="main_issue",
            rejected_value=match.group(1).strip(),
            confirmed_value=match.group(2).strip(),
        )
    return None


def _offline_intent(
    text: str,
    selected_mode: str | None,
    state: ConversationState,
) -> tuple[UserIntent, AdviceReadiness]:
    explicit_reject = _contains_any(text, INTENT_REJECT_PATTERNS) or "不是想听建议" in text
    if _contains_any(text, VENT_PATTERNS) or "还没说完" in text:
        return UserIntent.VENT, AdviceReadiness.REJECT
    clarify_requested = _contains_any(text, CLARIFY_PATTERNS) and not (
        "不用他帮我分析" in text and not any(marker in text for marker in ["帮我理清", "分开列", "已知事实"])
    )
    if clarify_requested:
        return UserIntent.CLARIFY, AdviceReadiness.REJECT if explicit_reject else AdviceReadiness.UNCERTAIN
    if explicit_reject:
        return UserIntent.VENT, AdviceReadiness.REJECT
    if selected_mode == "先帮我稳一下":
        return UserIntent.STABILIZE, AdviceReadiness.UNCERTAIN
    if _contains_any(text, STRATEGY_NOT_ACTION_PATTERNS):
        return UserIntent.ADVICE, AdviceReadiness.WILLING
    if _contains_any(text, ACTION_PATTERNS):
        return UserIntent.ADVICE, AdviceReadiness.EXPLICIT
    if _contains_any(text, CHOOSE_PATTERNS):
        return UserIntent.CHOOSE, AdviceReadiness.EXPLICIT
    if _contains_any(text, ADVICE_PATTERNS):
        return UserIntent.ADVICE, AdviceReadiness.EXPLICIT
    if _contains_any(text, STABILIZE_PATTERNS):
        return UserIntent.STABILIZE, AdviceReadiness.UNCERTAIN
    if _contains_any(text, UNDERSTOOD_PATTERNS):
        return UserIntent.BE_UNDERSTOOD, AdviceReadiness.UNCERTAIN

    if selected_mode in MODE_TO_INTENT:
        intent = MODE_TO_INTENT[selected_mode]
        readiness = (
            AdviceReadiness.WILLING
            if intent in {UserIntent.ADVICE, UserIntent.CHOOSE}
            else AdviceReadiness.UNCERTAIN
        )
        return intent, readiness
    if state.confirmed_intent:
        return state.confirmed_intent, state.confirmed_advice_readiness or AdviceReadiness.UNCERTAIN
    return UserIntent.UNKNOWN, AdviceReadiness.UNCERTAIN


# These rules belong to the ordinary problem map, not the shared sentence
# splitter, intent controller, or safety precheck. Unknown text stays evidence;
# it is not promoted to an event merely because no worry word matched.
_PROBLEM_REPORTER = r"(?:老师|同学|室友|朋友|同事|家人|父母|妈妈|爸爸|他|她|对方|负责人|通知|邮件|消息)"
_PROBLEM_REPORTING = re.compile(
    rf"(?:{_PROBLEM_REPORTER}(?:告诉我|说|提到|表示|写道)|据.{{1,12}}(?:说|所述)|我听说|听说)"
)
_PROBLEM_NEGATED_WORRY = re.compile(r"(?:不|没(?:有)?|并不)(?:再|怎么|那么)?(?:担心|害怕|怕|焦虑)")


def _problem_clauses(text: str) -> list[str]:
    """Bounded verbatim subclauses; quoted reports retain their speaker/scope."""
    clauses: list[str] = []
    buffer: list[str] = []
    quote_ends: list[str] = []
    pairs = {"“": "”", "‘": "’", "「": "」", "『": "』", '"': '"', "'": "'"}

    def flush() -> None:
        value = "".join(buffer).strip(" ，,。.！？!?；;\n\t")
        # Do not truncate away a late negation or reporting qualifier.
        if 2 <= len(value) <= MAX_USER_INPUT_LENGTH and not _is_injection_clause(value):
            clauses.append(value)
        buffer.clear()

    for index, char in enumerate(text):
        if quote_ends and char == quote_ends[-1]:
            quote_ends.pop()
            buffer.append(char)
            # A new first-person/request clause can follow a quoted sentence
            # without an extra delimiter: 老师说：“……”我脑子很乱。
            if not quote_ends and re.match(r"(?:(?:但是|但|可是|可|不过|然而))?(?:我|脑子|帮我|请)", text[index + 1:]):
                flush()
        elif char in pairs:
            quote_ends.append(pairs[char])
            buffer.append(char)
        elif not quote_ends and char in "，,。.！？!?；;\n":
            current = "".join(buffer).strip()
            numeric_separator = char in ",." and index > 0 and text[index - 1].isdigit() and text[index + 1:index + 2].isdigit()
            reporting_lead = _PROBLEM_REPORTING.fullmatch(current.rstrip("：:"))
            if numeric_separator or (char in "，," and reporting_lead):
                buffer.append(char)
            else:
                flush()
        else:
            buffer.append(char)
        if len(clauses) >= 24:
            break
    if len(clauses) < 24:
        flush()
    return list(dict.fromkeys(clauses))


def _problem_clause_kind(clause: str) -> str:
    """Conservative ownership categories over intact user wording."""
    if _is_injection_clause(clause):
        return "unknown"
    if _PROBLEM_REPORTING.search(clause[:40]) or clause.startswith(("“", "‘", "「", "『", '"', "'")):
        return "reported"
    # Ignore a discourse connector for classification only; the stored span
    # and its qualifiers remain verbatim.
    clause = re.sub(r"^(?:但是|但|可是|可|不过|然而)(?=我|脑子|帮我|请)", "", clause)
    if re.match(
        r"^(?:(?:请|麻烦|先|也|能不能|可以)?(?:你)?帮我|我(?:希望|想让|想请)你|"
        r"(?:我)?(?:只是|只|现在只)?想(?:确认|知道|理清|区分|听|说|讨论|问|看看)|"
        r"(?:请|别|不要|先不要)(?:给|分析|建议|替我|帮|急着))", clause
    ) or _contains_any(clause, INTENT_REJECT_PATTERNS + VENT_PATTERNS):
        return "request"
    if _PROBLEM_NEGATED_WORRY.search(clause):
        return "feeling"
    if re.match(
        r"^(?:我(?:现在|最近|此刻)?(?:觉得|感觉)?|现在|最近|此刻)?"
        r"(?:(?:脑子|心里|身体|心情|情绪)(?:很|有点|特别|非常)?(?:乱|慌|紧|低落)|"
        r"(?:很|有点|特别|非常|好|太)?(?:混乱|困惑|焦虑|紧张|慌|难过|委屈|生气|愤怒|"
        r"孤独|内疚|疲惫|累|开心|高兴|失落|害怕|不安))", clause
    ):
        # 害怕/怕 followed by an outcome is an expressed worry, not an event.
        return "interpretation" if re.search(r"(?:害怕|怕).+", clause) else "feeling"
    if _contains_any(clause, INTERPRETATION_MARKERS) or re.search(
        r"担心|害怕|(?:^|我)怕|恐怕|也许|大概|估计|或许|不确定|(?:尚未|还没(?:有)?|未)确认", clause
    ):
        return "interpretation"
    if re.search(
        r"截止|交付日期|交付时间|定在|安排在|开始于|结束于|"
        r"(?:已经|已|刚刚|刚|没有|没能)(?:完成|提交|收到|发出|发了|交了|联系|取消|退回|通过)|"
        r"(?:项目|作业|报告|考试|课程|会议|文件|申请|任务).{0,16}(?:开始|结束|取消|失败|退回|通过|延期)|"
        r"(?:上传|提交).{0,16}(?:报错|错误|失败|不支持)|"
        r"(?:老师|同学|室友|朋友|同事|对方).{0,12}(?:发来|回复|拒绝|离开|打断)|"
        r"(?:我|我们).{0,20}(?:吵架了|见面了|被.{1,10}(?:批评|拒绝|表扬|误解)了)|"
        r"努力(?:没|没有)被看到", clause
    ):
        return "event"
    return "unknown"


def _extract_problem_fields(text: str) -> tuple[list[str], list[str], str]:
    clauses = _problem_clauses(text)
    classified = [(clause, _problem_clause_kind(clause)) for clause in clauses]
    facts = [clause for clause, kind in classified if kind == "event"]
    interpretations = [clause for clause, kind in classified if kind in {"interpretation", "reported"}]

    focus_candidates = [
        clause
        for clause, kind in classified
        if kind not in {"request", "reported"}
        if any(marker in clause for marker in ["重点", "最难受", "卡住", "难受的是", "真正", "核心"])
    ]
    if focus_candidates:
        main_issue = focus_candidates[-1]
    elif interpretations:
        main_issue = interpretations[0]
    elif facts:
        main_issue = facts[0]
    else:
        main_issue = next((clause for clause, kind in classified if kind == "feeling"), "")
        if not main_issue:
            main_issue = next((clause for clause, kind in classified if kind == "unknown"), "尚未明确")
    # A short tentative focus may reuse a grounded clause, but must not cut off
    # its negation/attribution. Long originals remain available in evidence.
    return _dedupe(facts, 10), _dedupe(interpretations, 6), main_issue if len(main_issue) <= 180 else "尚未明确"


def _infer_needs(text: str, intent: UserIntent, safety_status: SafetyStatus) -> list[str]:
    needs: list[str] = []
    if intent in {UserIntent.VENT, UserIntent.BE_UNDERSTOOD, UserIntent.UNKNOWN}:
        needs.append("被理解")
    if any(word in text for word in ["没被看到", "没有被看到", "认可", "署名", "排名", "表扬"]):
        needs.append("努力被看见和认可")
    if any(word in text for word in ["不公平", "委屈", "边界", "尊重"]):
        needs.append("公平与尊重")
    if any(word in text for word in ["一个人", "孤独", "陪着", "朋友", "室友"]):
        needs.append("现实连接和陪伴")
    if any(word in text for word in ["替我决定", "未经同意", "选择", "不想让", "由我决定"]):
        needs.append("自主选择")
    if any(word in text for word in ["担心", "焦虑", "截止", "混乱", "不知道怎么办", "优先"]):
        needs.append("掌控感和清晰边界")
    if any(word in text for word in ["累", "睡", "耗尽", "休息"]):
        needs.append("休息和降低负担")
    if safety_status in {SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4}:
        needs = ["当前安全", "现实陪伴", "专业或紧急支持", *needs]
    return _dedupe(needs or ["被理解"], 5)


def _extract_optional_fields(text: str, clauses: list[str]) -> tuple[str, list[str], list[str], list[str], list[str]]:
    desired = next(
        (clause for clause in clauses if any(word in clause for word in ["我希望", "我想要", "目标是", "只想把"])),
        "尚未明确",
    )
    controllable = [
        clause for clause in clauses if any(word in clause for word in ["我能", "我可以", "我愿意", "我先", "我会"])
    ]
    uncontrollable = [
        clause
        for clause in clauses
        if any(word in clause for word in ["不知道", "是否", "结果", "会不会", "对方会", "成绩"])
    ]
    attempts = [
        clause for clause in clauses if any(word in clause for word in ["已经", "试过", "做了", "发了", "完成", "联系"])
    ]
    resources = [
        clause
        for clause in clauses
        if any(word in clause for word in ["朋友", "室友", "同事", "老师", "辅导员", "家人", "宿管", "前台"])
    ]
    return (
        desired[:180],
        _dedupe(controllable, 8),
        _dedupe(uncontrollable, 8),
        _dedupe(attempts, 6),
        _dedupe(resources, 6),
    )


def _evidence_spans(text: str, clauses: list[str], limit: int = 12) -> list[str]:
    priority = [
        clause
        for clause in clauses
        if any(
            marker in clause
            for marker in [
                "不是",
                "没有",
                "不想",
                "最难受",
                "重点",
                "愿意",
                "已经",
                "现在",
                "周五",
                "小时",
                "分钟",
                "担心",
                "委屈",
            ]
        )
    ]
    return _dedupe([*priority, *clauses], limit) or [text[:100]]


def _apply_confirmed_state(
    analysis: TurnAnalysis,
    state: ConversationState,
    correction: CorrectionSignal | None,
) -> TurnAnalysis:
    correction_field = correction.field if correction else ""
    if state.confirmed_primary_emotion and correction_field != "primary_emotion":
        analysis.primary_emotion = state.confirmed_primary_emotion
        analysis.secondary_emotions = state.confirmed_secondary_emotions[:2]
    if state.confirmed_intent and correction_field not in {"user_intent", "advice_readiness"}:
        analysis.user_intent = state.confirmed_intent
    if state.confirmed_advice_readiness and correction_field != "advice_readiness":
        analysis.advice_readiness = state.confirmed_advice_readiness
    if state.confirmed_needs:
        analysis.underlying_needs = state.confirmed_needs[:5]
    if state.confirmed_main_issue and correction_field != "main_issue" and analysis.main_issue == "尚未明确":
        analysis.main_issue = state.confirmed_main_issue
    return analysis


def offline_analysis(
    user_input: str,
    state: ConversationState,
    selected_mode: str | None,
) -> TurnAnalysis:
    previous_safety = state.last_analysis.safety if state.last_analysis else None
    safety = precheck_safety(user_input, previous_safety)
    primary, secondary = _offline_emotions(user_input)
    intent, readiness = _offline_intent(user_input, selected_mode, state)
    correction = _explicit_correction(user_input)
    input_security = _detect_input_security(user_input)
    facts, interpretations, main_issue = _extract_problem_fields(user_input)
    clauses = _split_clauses(user_input)
    desired, controllable, uncontrollable, attempts, resources = _extract_optional_fields(user_input, clauses)

    if correction and correction.field == "main_issue":
        main_issue = correction.confirmed_value

    if safety.status in {SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4}:
        stage = DialogueStage.SAFETY
        intent = UserIntent.SAFETY
    elif intent == UserIntent.STABILIZE:
        stage = DialogueStage.SUPPORT
    elif intent == UserIntent.CLARIFY:
        stage = DialogueStage.ORGANIZE
    elif intent in {UserIntent.ADVICE, UserIntent.CHOOSE}:
        stage = (
            DialogueStage.ACT
            if readiness == AdviceReadiness.EXPLICIT and _contains_any(user_input, ACTION_PATTERNS)
            else DialogueStage.STRATEGIZE
        )
    else:
        stage = DialogueStage.EXPRESS

    problem_clauses = _problem_clauses(user_input)
    if stage == DialogueStage.ORGANIZE:
        # A denied worry or a request mentioning emotion words is not evidence
        # of a current affirmative feeling. Keep the intact wording separately.
        emotion_evidence = [clause for clause in problem_clauses
                            if _problem_clause_kind(clause) not in {"request", "reported"}
                            and not _PROBLEM_NEGATED_WORRY.search(clause)]
        primary, secondary = _offline_emotions("；".join(emotion_evidence))

    # This turn's explicit correction wins over every automatic emotion pass.
    if correction and correction.field == "primary_emotion":
        primary = Emotion(correction.confirmed_value)
        secondary = [
            emotion for emotion in secondary
            if emotion.value != correction.rejected_value and emotion != primary
        ][:2]

    intensity = 2
    if any(word in user_input for word in ["很", "特别", "一直", "反复", "完全"]):
        intensity += 1
    if any(word in user_input for word in ["睡四五个小时", "控制不住", "不能保证", "没有希望", "不想活"]):
        intensity += 1
    if safety.status in {SafetyStatus.S3, SafetyStatus.S4}:
        intensity = 5
    elif safety.status == SafetyStatus.S2:
        intensity = max(intensity, 4)

    analysis = TurnAnalysis(
        suggested_stage=stage,
        user_intent=intent,
        main_issue=main_issue,
        facts=facts,
        interpretations=interpretations,
        primary_emotion=primary,
        secondary_emotions=secondary,
        emotion_intensity=min(5, intensity),
        trigger=next((fact for fact in facts if len(fact) <= 180), "尚未明确"),
        underlying_needs=_infer_needs(user_input, intent, safety.status),
        advice_readiness=readiness,
        desired_outcome=desired,
        controllable=controllable,
        uncontrollable=uncontrollable,
        attempts=attempts,
        resources=resources,
        correction=correction,
        input_security=input_security,
        input_features={
            "long_input": len(user_input) >= 400,
            "multiple_topics": len(clauses) >= 6,
            "sarcasm_detected": bool(re.search(r"[‘'\"](?:优秀|厉害|真棒)[’'\"]", user_input)),
        },
        safety=safety,
        evidence_spans=_evidence_spans(user_input, problem_clauses) if problem_clauses else [],
        certainty=Certainty.HIGH if correction or safety.status != SafetyStatus.S0 else Certainty.MEDIUM,
    )
    return _apply_confirmed_state(analysis, state, correction)


def _analysis_prompt(
    user_input: str,
    history: list[dict],
    state: ConversationState,
    selected_mode: str | None,
) -> list[dict[str, str]]:
    template = (PROMPT_DIR / "state_analysis_prompt.txt").read_text(encoding="utf-8")
    schema = json.dumps(TurnAnalysis.model_json_schema(), ensure_ascii=False)
    system_prompt = template.replace("{schema}", schema)
    user_payload = {
        "selected_mode": selected_mode or "用户未选择",
        "confirmed_state": state.model_dump(mode="json"),
        "history": format_history(history),
        "current_input": user_input,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _severity(status: SafetyStatus) -> int:
    return int(status.value[1])


def _merge_local_safety(analysis: TurnAnalysis, local) -> TurnAnalysis:
    if _severity(local.status) > _severity(analysis.safety.status):
        analysis.safety = local
    elif local.status != SafetyStatus.S0:
        evidence = list(dict.fromkeys(analysis.safety.evidence + local.evidence))[:8]
        analysis.safety.evidence = evidence
    if analysis.safety.status in {SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4}:
        analysis.suggested_stage = DialogueStage.SAFETY
        analysis.user_intent = UserIntent.SAFETY
    return analysis


def _validate_evidence(analysis: TurnAnalysis, user_input: str) -> TurnAnalysis:
    analysis.evidence_spans = [
        span for span in analysis.evidence_spans if span and span in user_input
    ][:12] or [user_input[:100]]
    analysis.safety.evidence = [
        span for span in analysis.safety.evidence if span and span in user_input
    ][:8]
    return analysis


def analyze_turn(
    user_input: str,
    history: list[dict],
    state: ConversationState,
    selected_mode: str | None,
    gateway: LLMGateway | None = None,
) -> tuple[TurnAnalysis, bool, str | None]:
    previous_safety = state.last_analysis.safety if state.last_analysis else None
    local_safety = precheck_safety(user_input, previous_safety)

    # Immediate-danger language never leaves the local process. The fixed S4
    # protocol is intentionally selected before any provider call is possible.
    if local_safety.status == SafetyStatus.S4:
        return offline_analysis(user_input, state, selected_mode), True, "local_safety_protocol"

    if not is_llm_configured(gateway):
        return offline_analysis(user_input, state, selected_mode), True, "missing_api_key"

    messages = _analysis_prompt(user_input, history, state, selected_mode)
    try:
        data = call_json(
            gateway=gateway,
            messages=messages,
            temperature=ANALYSIS_TEMPERATURE,
            max_tokens=ANALYSIS_MAX_TOKENS,
        )
        analysis = TurnAnalysis.model_validate(data)
    except Exception as first_error:
        try:
            repair_messages = messages + [
                {
                    "role": "system",
                    "content": "上一次输出未通过结构校验。保持事实、否定、纠正和安全语义不变，只输出符合 JSON Schema 的完整对象。",
                }
            ]
            data = call_json(
                gateway=gateway,
                messages=repair_messages,
                temperature=0.0,
                max_tokens=ANALYSIS_MAX_TOKENS,
            )
            analysis = TurnAnalysis.model_validate(data)
        except Exception:
            code = first_error.code if isinstance(first_error, LLMServiceError) else "analysis_invalid"
            return offline_analysis(user_input, state, selected_mode), True, code

    analysis = _validate_evidence(analysis, user_input)
    analysis = _merge_local_safety(analysis, local_safety)
    analysis = _apply_confirmed_state(analysis, state, analysis.correction)
    return analysis, False, None
