from __future__ import annotations

import hashlib

from modules.models import (
    ActionPlan,
    AdviceReadiness,
    DialogueStage,
    TurnAnalysis,
    TurnPlan,
    UserIntent,
)
from modules.state_analyzer import _problem_clause_kind, _problem_clauses


TEMPLATES: dict[str, tuple[str, ...]] = {
    "邀请表达": (
        "我先接住你提到的{mentioned}。这一轮不急着分析，也不要求马上得出结论；你可以从最占注意力的部分继续说。",
        "目前最清楚的一点是{mentioned}。我们先把空间留给你的表达，不列方案；你想按什么顺序说都可以。",
        "你刚才把{mentioned}放到了这里。我先不替你解释原因，也不推进下一步，继续听你把重要的部分说完整。",
        "这轮先停在{mentioned}这里，不催你解决，也不把感受整理成任务。你可以慢一点，把还没说完的部分接着说。",
    ),
    "具体复述": (
        "我目前听到的是：{fact}。真正牵住你的可能是“{issue}”，我先按这个重点陪你往下说。",
        "先只复述已经出现的内容：{fact}。它和“{issue}”连在一起，但更深原因还需要由你确认。",
        "你描述的具体处境是“{fact}”；现在最突出的卡点是“{issue}”。我不会把这份暂定理解当成结论。",
        "我先把刚才那段压缩成一句：{fact}，而你最放不下的是“{issue}”。如果有偏差，以你的纠正为准。",
    ),
    "澄清问题": (
        "围绕“{issue}”，我先只确认一个重点：这件事里哪一部分最让你放不下？",
        "现在不扩展到其他问题，只看“{issue}”：你最希望我先弄清楚的是哪一点？",
        "为了不把重点理解偏，我只问一个问题：当你想到“{issue}”时，最担心随之发生什么？",
        "我们先把范围收小。关于“{issue}”，此刻最需要被说清的是事实、感受，还是你担心的后果？",
    ),
    "总结问题地图": (
        "先分开来看：{event_map}{interpretation_map}{feeling_map}{request_map}{context_map}这样区分准确吗？",
        "按你提供的信息梳理：{event_map}{interpretation_map}{feeling_map}{request_map}{context_map}需要调整哪一处？",
        "这轮先整理问题地图：{event_map}{interpretation_map}{feeling_map}{request_map}{context_map}我理解得对吗？",
        "先梳理，不急着解决：{event_map}{interpretation_map}{feeling_map}{request_map}{context_map}这份区分合适吗？",
    ),
    "情绪反映": (
        "听起来，“{fact}”带来的不只是{emotion}，还让“{issue}”一直压在心里。先不用急着处理它。",
        "你面对的是“{fact}”，这里最明显的是{emotion}；它和你在意的“{need}”连在一起。",
        "我听见的重点不是一个抽象标签，而是“{fact}”之下的{emotion}。这份感受值得先被认真对待。",
        "当“{fact}”和“{interpretation}”同时出现时，{emotion}会变得很突出。我先陪你停在这里。",
    ),
    "情绪验证": (
        "在“{fact}”这样的处境里，出现{emotion}是可以理解的；这不等于你必须认同所有担心，也不要求马上想开。",
        "你在意的是“{need}”，所以面对“{fact}”时感到{emotion}并不奇怪。我们先承认这份感受确实存在。",
        "“{fact}”已经占用了你很多注意力。此刻的{emotion}有它的处境来源，不需要先证明自己有没有资格这样难受。",
        "这里可以同时保留两件事：事实仍需确认，而你因“{fact}”产生的{emotion}也是真实需要被接住的。",
    ),
    "力量确认": (
        "即使“{issue}”还没有解决，你已经把“{fact}”说得很具体；能分辨这些内容，本身就是可用的力量。",
        "我不会用空泛鼓励盖过困难。至少此刻，你已经愿意面对“{issue}”并补充事实，这是可以确认的努力。",
        "结果尚未确定，但你已经做到了把“{fact}”带进对话，而不是继续独自扛着；这一点值得被看见。",
        "你不需要被保证一定成功。现在能确认的是，你正在尝试理解“{issue}”，也保留了调整下一步的主动权。",
    ),
    "短时稳定": (
        "现在先不处理“{issue}”。把双脚踩实地面，找一个固定物体看着，慢慢呼气三次；做完只判断紧绷有没有变化。",
        "这一轮只做短时稳定：肩膀放松一点，呼气比吸气稍长，连续三次。暂时不分析原因，也不安排复杂任务。",
        "先把注意力放回当下：说出眼前看到的三样东西，再做一次缓慢呼气。目标不是立刻平静，只是降低一点混乱。",
        "暂时把“{issue}”放在一边。双手接触桌面或衣物，感受触感十秒，再缓慢呼气；只完成这一个动作即可。",
    ),
    "征求建议许可": (
        "关于“{goal}”，我可以继续陪你梳理，也可以提供两三个可比较的方向。你现在愿意进入方案讨论吗？",
        "我已经听到你想处理“{issue}”。在给出办法前先确认：你希望这轮开始看选项，还是再把问题说清一点？",
        "这里确实出现了可讨论的方向，但决定权在你。现在要不要先看不超过三个备选，而不立即做决定？",
        "如果你愿意，我们可以围绕“{goal}”比较几个现实方向；如果还没准备好，也可以停在梳理。你更倾向哪边？",
    ),
    "提供信息": (
        "先补一条决策信息：可以把“{issue}”拆成已知、待核实和不可控三栏；目前最值得先核实的是会改变选择的那个未知点。",
        "围绕“{goal}”，信息支持应先服务于判断，而不是堆知识。可以先确认截止、责任或可调整范围中的一个关键条件。",
        "这一轮不直接替你决定。先找一条会改变后续方案的事实，例如时间边界、对方要求或现有资源，再据此比较。",
        "与其一次搜集所有信息，不如只补“{issue}”中最关键的未知条件；得到答案后，再决定是否进入行动。",
    ),
    "比较方案": (
        "围绕“{goal}”，可以先比较三个方向：{options}。这轮只选一个最接近现实条件的方向，最后决定权仍在你。",
        "我们不一次解决全部，只把选项并排放好：{options}。可以按可行性、代价和可逆性选一个先看。",
        "现在有几个可能入口：{options}。先判断哪一个最能增加掌控感，不要求今天把后续全部完成。",
        "关于“{issue}”，备选方向是：{options}。你可以先排除明显不合适的一项，再看剩下哪个更能做到。",
    ),
    "最小行动": (
        "只落实一个小步骤：{action}。时间是{when}，地点是{location}，限时{duration}分钟；完成标准是{success}。若遇到{obstacle}，就{fallback}。",
        "把行动缩到可以开始：在{when}、{location}完成“{action}”，只做{duration}分钟。做到{success}就停止；卡住时改为{fallback}。",
        "本轮行动卡只保留一件事：{action}。用时上限{duration}分钟，完成标准不是做好全部，而是{success}；主要障碍出现时，{fallback}。",
        "下一步定得足够小：{when}在{location}{action}，到{duration}分钟立即停。只要{success}就算完成；如果难以开始，{fallback}。",
    ),
    "回顾调整": (
        "先不评价成败，只回顾上次行动：实际开始了多少、卡在什么位置。根据结果只调整时长、动作或环境中的一个变量。",
        "这轮不是重新制定大计划，而是检查小步骤是否过大。保留有效部分，把最卡的一处缩小，然后再决定是否继续。",
        "回顾只看事实：有没有开始、用了多久、阻碍是什么。若没有完成，就把动作缩短一半，不把它解释成能力问题。",
        "我们根据执行结果更新行动卡：先记录顺利处和卡点，再选择一个最小调整；不追加新的任务清单。",
    ),
}


SECONDARY_CLAUSES = {
    "邀请表达": "你可以按自己的顺序继续。",
    "具体复述": "这只是暂定复述，以你的确认为准。",
    "澄清问题": "这一轮只确认这一个重点。",
    "总结问题地图": "先确认地图，不急着解决。",
    "情绪反映": "我先不把它压缩成一个标签。",
    "情绪验证": "验证感受不等于确认所有推测。",
    "力量确认": "这里确认的是已经发生的努力。",
    "短时稳定": "目标只是让当下稍微可承受一点。",
    "征求建议许可": "不愿意时可以继续停在表达。",
    "提供信息": "只补会改变决定的一条信息。",
    "比较方案": "选择仍由你决定。",
    "最小行动": "完成后不追加任务。",
    "回顾调整": "没有完成也只调整步骤，不评价自己。",
}


def _short(value: str, limit: int) -> str:
    cleaned = str(value or "").strip(" ，。！？；;:\n\t")
    if not cleaned:
        return "尚未明确"
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _stable_index(user_input: str, turn_index: int, strategy: str, size: int) -> int:
    digest = hashlib.sha256(f"{user_input.strip()}|{turn_index}|{strategy}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def _compose_problem_map(analysis: TurnAnalysis, template: str, budget: int) -> str:
    # Keep feeling and request evidence separate from statements about events.
    # Quoted/reported clauses remain intact in the analyzer's local splitter.
    evidence = list(dict.fromkeys(
        clause for span in analysis.evidence_spans for clause in _problem_clauses(span)
    ))
    source = {
        "event": analysis.facts,
        "interpretation": analysis.interpretations,
        "feeling": [item for item in evidence if _problem_clause_kind(item) == "feeling"],
        "request": [item for item in evidence if _problem_clause_kind(item) == "request"],
        "context": [item for item in evidence if _problem_clause_kind(item) == "unknown"
                    and item not in analysis.facts and item not in analysis.interpretations],
    }
    values = {key: items[:1 if key == "context" else 2] for key, items in source.items()}
    omitted = {key: len(source[key]) > len(items) for key, items in values.items()}
    unquoted: set[str] = set()
    labels = {
        "event": "事件",
        "interpretation": "担忧、推测或转述",
        "feeling": "感受",
        "request": "请求",
        "context": "其他表述",
    }

    def render() -> str:
        excerpts = {key: "；".join(items) for key, items in values.items()}
        event = f"你提到“{excerpts['event']}”；" if values["event"] else "具体事件尚未明确；"
        reported = bool(values["interpretation"]) and all(
            _problem_clause_kind(item) == "reported" for item in values["interpretation"]
        )
        has_reported = any(_problem_clause_kind(item) == "reported" for item in values["interpretation"])
        if reported:
            interpretation = f"你转述“{excerpts['interpretation']}”，内容仍待确认；"
        elif has_reported:
            interpretation = f"你提到的担忧、推测或转述是“{excerpts['interpretation']}”，内容未据此确认；"
        elif values["interpretation"]:
            interpretation = f"你表达的担忧/推测是“{excerpts['interpretation']}”，结果未据此确认；"
        else:
            interpretation = "担忧或解释暂未明确；"
        feeling = f"你自述的感受是“{excerpts['feeling']}”；" if values["feeling"] else ""
        request = f"这轮请求是“{excerpts['request']}”；" if values["request"] else ""
        context = f"你还提到“{excerpts['context']}”，这部分尚待厘清；" if values["context"] else ""
        slots = {"event": event, "interpretation": interpretation, "feeling": feeling, "request": request, "context": context}
        for key in slots:
            if key in unquoted:
                slots[key] = f"{labels[key]}原文较长，暂不截取；"
            elif omitted[key]:
                slots[key] += "另有该类信息未展开；"
        return template.format(**{f"{key}_map": value for key, value in slots.items()})

    response = render()
    # Never truncate a proposition: a negation or speaker attribution may be at
    # its end. Omit whole extra clauses first, then acknowledge an overlong
    # clause without quoting a potentially misleading fragment of it.
    while len(response) > budget and any(len(items) > 1 for items in values.values()):
        largest = max((key for key in values if len(values[key]) > 1), key=lambda key: len(values[key][-1]))
        values[largest].pop()
        omitted[largest] = True
        response = render()
    while len(response) > budget and any(items and key not in unquoted for key, items in values.items()):
        largest = max(
            (key for key, items in values.items() if items and key not in unquoted),
            key=lambda key: len("；".join(values[key])),
        )
        unquoted.add(largest)
        response = render()
    if len(response) > budget:
        return "部分原文较长，暂不截取，也不把片段当成结论。你希望先澄清哪一段？"
    return response


def compose_strategy_response(
    analysis: TurnAnalysis,
    plan: TurnPlan,
    *,
    user_input: str,
    turn_index: int,
    prefix: str = "",
    action: ActionPlan | None = None,
) -> str:
    strategy = plan.primary_strategy
    variants = TEMPLATES.get(strategy) or TEMPLATES["具体复述"]
    fact = _short(analysis.facts[0] if analysis.facts else "尚未说明具体事件", 52)
    issue = _short(analysis.main_issue, 42)
    interpretation = _short(
        analysis.interpretations[0] if analysis.interpretations else "尚未有足够证据确认更深原因",
        46,
    )
    emotions = [analysis.primary_emotion.value, *[item.value for item in analysis.secondary_emotions[:1]]]
    emotion = "和".join(item for item in emotions if item != "中性") or "平常的感受"
    need = "、".join(analysis.underlying_needs[:2]) or "被理解"
    goal = _short(
        analysis.desired_outcome if analysis.desired_outcome != "尚未明确" else analysis.main_issue,
        48,
    )
    options = [_short(item, 38) for item in analysis.controllable[:3]]
    for default in ("核实一个关键未知信息", "区分可控和不可控部分", "做一次范围或边界确认"):
        if len(options) >= 3:
            break
        if default not in options:
            options.append(default)
    option_text = "；".join(f"{index + 1}.{item}" for index, item in enumerate(options[:3]))
    action = action or ActionPlan(action=f"把“{issue}”写成一个十分钟内可以开始的第一步")
    # An invitation may acknowledge feelings/requests as things the user said,
    # without promoting them into the event-only fact slot. Keep whole spans.
    mention = next((clause for span in analysis.evidence_spans for clause in _problem_clauses(span)
                    if len(clause) <= 52), "")
    slots = {
        "fact": fact,
        "mentioned": f"“{mention}”" if mention else "你刚才的表达",
        "issue": issue,
        "interpretation": interpretation,
        "emotion": emotion,
        "need": need,
        "goal": goal,
        "options": option_text,
        "action": action.action,
        "when": action.when,
        "location": action.location,
        "duration": action.duration_minutes,
        "success": action.success_criterion,
        "obstacle": action.obstacle,
        "fallback": action.fallback,
    }
    template = variants[_stable_index(user_input, turn_index, strategy, len(variants))]
    secondary = plan.secondary_strategy
    secondary_clause = (
        SECONDARY_CLAUSES.get(secondary, "") if secondary and secondary != strategy else ""
    )
    if strategy == "总结问题地图":
        chosen = _compose_problem_map(analysis, template, plan.max_chars - len(prefix) - len(secondary_clause))
    else:
        chosen = template.format(**slots)

    # An explicit request to vent must never be turned into a question or advice.
    if plan.stage == DialogueStage.EXPRESS and (
        analysis.advice_readiness == AdviceReadiness.REJECT or analysis.user_intent == UserIntent.VENT
    ):
        chosen = TEMPLATES["邀请表达"][
            _stable_index(user_input, turn_index, "邀请表达", len(TEMPLATES["邀请表达"]))
        ].format(**slots)

    if secondary and secondary != strategy and secondary in SECONDARY_CLAUSES:
        clause = SECONDARY_CLAUSES[secondary]
        if clause not in chosen:
            chosen = f"{chosen}{clause}"
    return prefix + chosen
