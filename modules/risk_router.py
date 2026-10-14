from __future__ import annotations

import re

from config import (
    DIRECT_SELF_HARM_PHRASES,
    HIGH_DISTRESS_PHRASES,
    INDIRECT_CRISIS_PHRASES,
)
from modules.models import SafetySignal, SafetyStatus
from utils.text_utils import normalize_for_rules


DISCUSSION_MARKERS = [
    "媒体素养课",
    "新闻里在讨论",
    "新闻中讨论",
    "讨论自杀预防的新闻",
    "文章里讨论",
    "论文研究",
    "研究危机语言",
    "心理课",
    "课堂材料",
    "课程里讨论",
    "自杀预防新闻",
    "电影角色",
    "电影里的角色",
    "电视剧角色",
    "影视台词",
    "案例中的",
    "幻灯片引用",
]
NON_SELF_CONTEXT_MARKERS = [
    "不是我的情况",
    "不是我本人",
    "我本人没事",
    "我自己没有",
    "只是引用",
    "虚构人物",
    "用于研究",
    "合成样例",
]
SELF_CURRENT_PATTERNS = [
    "我不想活",
    "我想死",
    "我想自杀",
    "我有伤害自己的想法",
    "我想伤害自己",
    "我有结束生命的想法",
    "我不能保证自己安全",
    "我控制不住自己",
]
NEGATION_PATTERNS = [
    "我并不想死",
    "我不想死",
    "我没有想死",
    "我没有自杀",
    "我不会自杀",
    "我没想伤害自己",
    "我没有伤害自己的想法",
    "不是想伤害自己",
    "我没有结束生命的想法",
    "没有结束生命的想法",
    "不是想结束生命",
    "现在没有这个想法",
    "现在没有自伤想法",
    "目前没有相关想法",
]
HISTORY_MARKERS = ["以前", "曾经", "过去", "之前", "上学期", "几个月前", "那时候"]
CURRENT_NEGATION_MARKERS = [
    "现在没有",
    "现在不",
    "目前没有",
    "已经没有",
    "现在已经没有",
    "当前没有",
    "现在也没有",
    "过去三个月都没有了",
]
OTHER_HARM_MARKERS = ["让他去死", "让她去死", "杀了他", "杀了她", "伤害他", "伤害她", "伤害别人"]
OTHER_HARM_NEGATION_MARKERS = [
    "没有伤害他的打算",
    "没有伤害她的打算",
    "没有伤害对方的打算",
    "没有伤害他的意图",
    "没有伤害她的意图",
    "不会去找他",
    "不会去找她",
    "只是气话",
]
OTHER_HARM_RETRACTION_MARKERS = ["撤回", "只是气话", "说得很过头", "不该这样说"]
HYPOTHETICAL_FUTURE_MARKERS = ["如果以后", "如果未来", "假如以后", "以后真的", "将来如果"]
CURRENT_THOUGHT_CONFIRM_MARKERS = [
    "有这个想法",
    "现在有这个想法",
    "现在有伤害自己的想法",
    "现在有结束生命的想法",
    "这个想法现在还在",
    "想法还在",
    "确实有结束生命的想法",
    "确实有伤害自己的想法",
    "是的",
    "有想过",
]
CURRENT_THOUGHT_DENIAL_MARKERS = [
    "只是想逃开",
    "只是太累",
    "只是想关掉",
    "没有这个想法",
    "不是想伤害自己",
    "没有结束生命的想法",
]
PLAN_POSITIVE_MARKERS = [
    "已经想好了伤害自己的具体计划",
    "已经想好了具体计划",
    "已经有具体计划",
    "有具体计划",
    "计划已经想好",
]
MEANS_POSITIVE_MARKERS = [
    "危险的东西已经在我手边",
    "危险的东西就在我手边",
    "东西就在我身边",
    "东西就在手边",
    "相关东西就在身边",
    "已经准备好了",
]
PLAN_NEGATION_MARKERS = ["没有具体计划", "还没有具体计划", "没有计划", "还没计划", "没想好完整计划"]
MEANS_NEGATION_MARKERS = [
    "没有准备",
    "没有能伤害自己的东西",
    "没有能马上用的东西",
    "身边也没放什么危险的东西",
    "没有可用手段",
    "书包里也没有",
]
UNSAFE_MARKERS = [
    "不能保证安全",
    "不能保证自己安全",
    "不能保证接下来",
    "控制不住自己",
    "马上控制不住",
    "马上要做",
    "已经决定了",
]
SAFE_ABILITY_MARKERS = [
    "能保证自己安全",
    "能继续保证安全",
    "能保证接下来",
    "先不伤害自己",
    "不会伤害自己",
    "可以保持安全",
]
REAL_SUPPORT_MARKERS = [
    "朋友已经在来",
    "姐姐已经出发",
    "姐姐已经到了",
    "室友就在",
    "工作人员在旁边",
    "辅导员会来",
    "宿管已经到了",
    "前台工作人员",
    "急救人员已经到了",
]
STABILIZATION_DISTRESS_MARKERS = [
    "心跳特别快",
    "手一直抖",
    "提纲一行都看不进去",
    "复杂的事情我完全想不了",
]
RECOVERY_TO_TASK_MARKERS = [
    "先把第一句说出来",
    "已经缓下来了",
    "现在能继续做",
    "可以回到刚才的任务",
]
POSITIVE_SELF_HARM_MARKERS = [
    "有伤害自己的想法",
    "想伤害自己",
    "有自伤想法",
]


def _contains(normalized_text: str, phrases: list[str]) -> list[str]:
    return [phrase for phrase in phrases if normalize_for_rules(phrase) in normalized_text]


def _positive_self_harm_hits(normalized_text: str) -> list[str]:
    hits: list[str] = []
    if re.search(r"(?<!没)有伤害自己的想法", normalized_text):
        hits.append("有伤害自己的想法")
    if re.search(r"(?<!不是)(?<!不)(?<!没)想伤害自己", normalized_text):
        hits.append("想伤害自己")
    if re.search(r"(?<!没)有自伤想法", normalized_text):
        hits.append("有自伤想法")
    return hits


def _third_party_markers(text: str) -> list[str]:
    named_pattern = re.compile(
        r"(?<!跟)(?<!对)(?<!向)(?:朋友|同学|室友|家人|哥哥|姐姐|弟弟|妹妹)"
        r".{0,16}(?:说|给我发|发给我|告诉我|提到|表示)"
    )
    pronoun_pattern = re.compile(r"(?:^|[，。；！!?])(?:他|她)(?:说|告诉我|提到|表示)")
    return [
        *[match.group(0) for match in named_pattern.finditer(text)],
        *[match.group(0) for match in pronoun_pattern.finditer(text)],
    ]


def _discussion_context(text: str, normalized: str, direct: list[str], indirect: list[str]) -> tuple[bool, list[str]]:
    markers = _contains(normalized, DISCUSSION_MARKERS)
    disclaimers = _contains(normalized, NON_SELF_CONTEXT_MARKERS)
    explicit_self_current = any(pattern in text for pattern in SELF_CURRENT_PATTERNS)
    if markers and (disclaimers or not explicit_self_current):
        return True, (markers + disclaimers + direct + indirect)[:8]
    return False, []


def _status_signal(
    *,
    status: SafetyStatus,
    subject: str = "本人",
    time_reference: str = "不明确",
    polarity: str = "无相关表达",
    harm_target: str = "无明确伤害对象",
    directness: str = "无",
    needs_clarification: bool = False,
    has_current_thoughts: bool | None = None,
    has_plan_or_means: bool | None = None,
    can_stay_safe: bool | None = None,
    evidence: list[str] | None = None,
    reason: str,
) -> SafetySignal:
    return SafetySignal(
        status=status,
        subject=subject,
        time_reference=time_reference,
        polarity=polarity,
        harm_target=harm_target,
        directness=directness,
        needs_clarification=needs_clarification,
        has_current_thoughts=has_current_thoughts,
        has_plan_or_means=has_plan_or_means,
        can_stay_safe=can_stay_safe,
        evidence=(evidence or [])[:8],
        reason=reason,
    )


def precheck_safety(
    user_input: str,
    previous: SafetySignal | None = None,
) -> SafetySignal:
    normalized = normalize_for_rules(user_input)
    previous = previous or SafetySignal()

    direct = _contains(normalized, DIRECT_SELF_HARM_PHRASES)
    indirect = _contains(normalized, INDIRECT_CRISIS_PHRASES)
    distress = _contains(normalized, HIGH_DISTRESS_PHRASES)
    stabilization_distress = _contains(normalized, STABILIZATION_DISTRESS_MARKERS)
    negated = _contains(normalized, NEGATION_PATTERNS)
    historical = _contains(normalized, HISTORY_MARKERS)
    current_negation = _contains(normalized, CURRENT_NEGATION_MARKERS)
    other_harm = _contains(normalized, OTHER_HARM_MARKERS)
    other_harm_negated = _contains(normalized, OTHER_HARM_NEGATION_MARKERS)
    other_harm_retracted = _contains(normalized, OTHER_HARM_RETRACTION_MARKERS)
    plan_positive = _contains(normalized, PLAN_POSITIVE_MARKERS)
    means_positive = _contains(normalized, MEANS_POSITIVE_MARKERS)
    plan_negated = _contains(normalized, PLAN_NEGATION_MARKERS)
    means_negated = _contains(normalized, MEANS_NEGATION_MARKERS)
    cannot_stay_safe = _contains(normalized, UNSAFE_MARKERS)
    hypothetical_future = _contains(normalized, HYPOTHETICAL_FUTURE_MARKERS)
    if hypothetical_future and not any(marker in user_input for marker in ["我现在", "此刻", "马上"]):
        cannot_stay_safe = []
    can_stay_safe = _contains(normalized, SAFE_ABILITY_MARKERS)
    support = _contains(normalized, REAL_SUPPORT_MARKERS)
    thought_confirmed = _contains(normalized, CURRENT_THOUGHT_CONFIRM_MARKERS)
    thought_denied = _contains(normalized, CURRENT_THOUGHT_DENIAL_MARKERS)

    is_discussion, discussion_evidence = _discussion_context(user_input, normalized, direct, indirect)
    if is_discussion:
        subject = "引用" if any(marker in user_input for marker in ["引用", "引号", "台词", "案例"]) else "话题讨论"
        return _status_signal(
            status=SafetyStatus.S0,
            subject=subject,
            time_reference="不适用",
            polarity="引用/教育/研究语境",
            directness="非本人陈述",
            evidence=discussion_evidence,
            reason="危机词属于新闻、课堂、影视、案例或研究内容，且无本人当前肯定表达",
        )

    if previous.status == SafetyStatus.S4:
        return _status_signal(
            status=SafetyStatus.S4,
            subject=previous.subject,
            time_reference="当前",
            polarity="紧急现实交接进行中",
            harm_target=previous.harm_target,
            directness="现实交接进行中",
            needs_clarification=False,
            has_current_thoughts=previous.has_current_thoughts,
            has_plan_or_means=previous.has_plan_or_means,
            can_stay_safe=previous.can_stay_safe,
            evidence=support or [user_input[:80]],
            reason="上一轮已进入 S4；在现实专业人员完成评估前不因用户开始求助而自动降级",
        )

    third_party = _third_party_markers(user_input)
    if third_party and (direct or indirect or thought_confirmed or previous.subject == "第三方"):
        third_plan = bool(plan_positive or means_positive) and not (plan_negated or means_negated)
        third_current = bool(thought_confirmed) or previous.status == SafetyStatus.S3
        if third_plan or cannot_stay_safe:
            return _status_signal(
                status=SafetyStatus.S4,
                subject="第三方",
                time_reference="当前",
                polarity="转述且紧迫",
                harm_target="第三方自伤",
                directness="当前紧迫危险",
                has_current_thoughts=True,
                has_plan_or_means=True if third_plan else None,
                can_stay_safe=False if cannot_stay_safe else None,
                evidence=third_party + plan_positive + means_positive + cannot_stay_safe,
                reason="第三方转述中出现具体计划、可用手段或无法安全，应立即连接现实紧急支持",
            )
        if third_current:
            return _status_signal(
                status=SafetyStatus.S3,
                subject="第三方",
                time_reference="当前",
                polarity="当前想法已确认的转述",
                harm_target="第三方自伤",
                directness="已确认相关想法",
                needs_clarification=True,
                has_current_thoughts=True,
                has_plan_or_means=False if plan_negated and means_negated else None,
                evidence=third_party + thought_confirmed + plan_negated + means_negated + support,
                reason="第三方当前相关想法仍在，需要现实人员继续确认和陪伴",
            )
        return _status_signal(
            status=SafetyStatus.S2,
            subject="第三方",
            time_reference="当前或最近",
            polarity="转述",
            harm_target="第三方自伤",
            directness="需澄清",
            needs_clarification=True,
            evidence=third_party + direct + indirect,
            reason="检测到第三方危机转述，计划手段和当前状态尚未厘清",
        )

    if other_harm:
        if previous.harm_target == "他伤" and (other_harm_negated or other_harm_retracted):
            return _status_signal(
                status=SafetyStatus.S1,
                subject="本人",
                time_reference="当前",
                polarity="他伤意图、计划和接触均否定",
                harm_target="他伤",
                directness="澄清后降级",
                has_current_thoughts=False,
                has_plan_or_means=False,
                can_stay_safe=True,
                evidence=other_harm + other_harm_negated + other_harm_retracted,
                reason="用户澄清或撤回愤怒气话，并无新的现实意图、计划或接触行为",
            )
        return _status_signal(
            status=SafetyStatus.S2,
            subject="本人",
            time_reference="当前",
            polarity="肯定或夸张表达",
            harm_target="他伤",
            directness="需澄清",
            needs_clarification=True,
            evidence=other_harm + other_harm_negated,
            reason="检测到他伤语境；即使同句出现否定，也先做一次直接澄清并与自伤分开",
        )

    if previous.harm_target == "他伤" and previous.status == SafetyStatus.S2 and other_harm_negated:
        return _status_signal(
            status=SafetyStatus.S1,
            subject="本人",
            time_reference="当前",
            polarity="他伤意图、计划和接触均否定",
            harm_target="他伤",
            directness="澄清后降级",
            has_current_thoughts=False,
            has_plan_or_means=False,
            can_stay_safe=True,
            evidence=other_harm_negated,
            reason="用户对上一轮他伤气话完成澄清，否认意图、计划、准备和接触",
        )

    if historical and (direct or indirect) and current_negation:
        return _status_signal(
            status=SafetyStatus.S1,
            subject="本人",
            time_reference="历史",
            polarity="历史肯定、当前否定",
            harm_target="自伤/结束生命",
            directness="历史表达",
            has_current_thoughts=False,
            evidence=historical + current_negation + direct + indirect,
            reason="存在历史相关想法，但用户明确否定当前想法",
        )

    positive_self_harm = _positive_self_harm_hits(normalized)
    if (negated or thought_denied) and not positive_self_harm:
        return _status_signal(
            status=SafetyStatus.S1,
            subject="本人",
            time_reference="当前",
            polarity="明确否定",
            harm_target="自伤/结束生命",
            directness="否定语境",
            needs_clarification=False,
            has_current_thoughts=False,
            has_plan_or_means=False if plan_negated or means_negated else None,
            can_stay_safe=True if can_stay_safe else None,
            evidence=negated + thought_denied + current_negation,
            reason="危机词位于本人明确否定或夸张逃避语境中，保留高困扰但不进入危机问询",
        )

    active_safety = previous.status in {SafetyStatus.S2, SafetyStatus.S3}
    if active_safety:
        if cannot_stay_safe or ((plan_positive or means_positive) and not (plan_negated or means_negated)):
            return _status_signal(
                status=SafetyStatus.S4,
                subject=previous.subject if previous.subject != "本人" else "本人",
                time_reference="当前",
                polarity="肯定",
                harm_target=previous.harm_target if previous.harm_target != "无明确伤害对象" else "自伤",
                directness="当前紧迫危险",
                has_current_thoughts=True,
                has_plan_or_means=True if plan_positive or means_positive else None,
                can_stay_safe=False if cannot_stay_safe else None,
                evidence=cannot_stay_safe + plan_positive + means_positive,
                reason="安全澄清中出现不能保证安全、具体计划或即时可用手段",
            )
        if thought_confirmed or direct:
            has_plan = False if plan_negated and means_negated else None
            safe_ability = True if can_stay_safe else None
            return _status_signal(
                status=SafetyStatus.S3,
                subject=previous.subject,
                time_reference="当前",
                polarity="肯定",
                harm_target=previous.harm_target if previous.harm_target != "无明确伤害对象" else "自伤",
                directness="已确认相关想法",
                needs_clarification=has_plan is None or safe_ability is None,
                has_current_thoughts=True,
                has_plan_or_means=has_plan,
                can_stay_safe=safe_ability,
                evidence=thought_confirmed + direct + plan_negated + means_negated + can_stay_safe + support,
                reason="用户在安全澄清中确认当前相关想法；保护信息不使其自动降级",
            )
        if previous.status == SafetyStatus.S3 and (plan_negated or means_negated or can_stay_safe or support):
            return _status_signal(
                status=SafetyStatus.S3,
                subject=previous.subject,
                time_reference="当前",
                polarity="当前想法背景仍在，保护信息已补充",
                harm_target=previous.harm_target,
                directness="安全连接进行中",
                needs_clarification=False,
                has_current_thoughts=True,
                has_plan_or_means=False if plan_negated and means_negated else previous.has_plan_or_means,
                can_stay_safe=True if can_stay_safe else previous.can_stay_safe,
                evidence=plan_negated + means_negated + can_stay_safe + support,
                reason="当前相关想法背景仍在，虽有保护信息和现实支持仍保持 S3",
            )

    if cannot_stay_safe:
        return _status_signal(
            status=SafetyStatus.S4,
            subject="本人",
            time_reference="当前",
            polarity="短时安全能力否定",
            harm_target="自伤",
            directness="当前紧迫危险",
            has_current_thoughts=True,
            has_plan_or_means=False if plan_negated and means_negated else None,
            can_stay_safe=False,
            evidence=cannot_stay_safe + plan_negated + means_negated,
            reason="用户明确无法保证短时安全；即使无计划手段也独立触发 S4",
        )

    if direct:
        urgent_plan = bool(plan_positive or means_positive) and not (plan_negated or means_negated)
        status = SafetyStatus.S4 if urgent_plan else SafetyStatus.S3
        return _status_signal(
            status=status,
            subject="本人",
            time_reference="当前" if thought_confirmed or urgent_plan else "不明确",
            polarity="肯定",
            harm_target="自伤/结束生命",
            directness="明确表达" if status == SafetyStatus.S3 else "当前紧迫危险",
            needs_clarification=status == SafetyStatus.S3,
            has_current_thoughts=True if thought_confirmed or urgent_plan else None,
            has_plan_or_means=True if urgent_plan else (False if plan_negated and means_negated else None),
            can_stay_safe=True if can_stay_safe else None,
            evidence=direct + thought_confirmed + plan_positive + means_positive + plan_negated + means_negated,
            reason=(
                "当前直接危机表达并出现具体计划或可用手段"
                if status == SafetyStatus.S4
                else "检测到本人直接危机表达，当前性、计划手段或短时安全仍需逐步确认"
            ),
        )

    if indirect:
        return _status_signal(
            status=SafetyStatus.S2,
            subject="本人",
            time_reference="不明确",
            polarity="含义不明确",
            harm_target="可能涉及自伤/结束生命",
            directness="间接表达",
            needs_clarification=True,
            evidence=indirect,
            reason="检测到需要一次直接澄清的间接危机表达",
        )

    if distress or stabilization_distress:
        return _status_signal(
            status=SafetyStatus.S1,
            subject="本人",
            time_reference="当前",
            polarity="高困扰",
            directness="无明确自伤表达",
            evidence=distress + stabilization_distress,
            reason="检测到明显高困扰语言，但没有当前自伤或死亡想法表达",
        )

    recovered_to_task = _contains(normalized, RECOVERY_TO_TASK_MARKERS)
    if previous.status == SafetyStatus.S1 and recovered_to_task:
        return SafetySignal(
            status=SafetyStatus.S0,
            subject="本人",
            time_reference="当前",
            polarity="已恢复到普通任务支持",
            directness="明确恢复信号",
            evidence=recovered_to_task[:8],
            reason="用户在短时稳定后明确恢复到普通任务行动，当前无持续高困扰或危机表达",
        )

    if previous.status == SafetyStatus.S1:
        return _status_signal(
            status=SafetyStatus.S1,
            subject=previous.subject,
            time_reference="当前",
            polarity=previous.polarity if previous.polarity != "无相关表达" else "高困扰延续",
            harm_target=previous.harm_target,
            directness="会话上下文延续",
            needs_clarification=False,
            has_current_thoughts=previous.has_current_thoughts,
            has_plan_or_means=previous.has_plan_or_means,
            can_stay_safe=previous.can_stay_safe,
            evidence=support or [user_input[:80]],
            reason="上一轮高困扰或澄清后的 S1 状态仍在当前会话中延续，未出现足以清零的新证据",
        )

    return SafetySignal()
