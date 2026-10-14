from __future__ import annotations

import json
import re

from config import (
    PROMPT_DIR,
    RESPONSE_MAX_TOKENS,
    RESPONSE_TEMPERATURE,
    SAFETY_RESOURCE_PATH,
)
from modules.llm_client import LLMGateway, LLMServiceError, call_json, is_llm_configured
from modules.choices import displayed_options, option_duration
from modules.models import (
    ActionPlan,
    AdviceReadiness,
    ConversationState,
    DialogueStage,
    GeneratedResponse,
    SafetyStatus,
    TurnAnalysis,
    TurnPlan,
    UserIntent,
)
from modules.response_composer import compose_strategy_response
from utils.text_utils import format_history, visible_char_count


def _resources() -> dict:
    try:
        return json.loads(SAFETY_RESOURCE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "psychological_support": "12356",
            "police": "110",
            "medical_emergency": "120",
            "campus_support": "学校辅导员或心理中心",
            "trusted_contact": "能实际到场的家人、朋友、老师或其他可信任者",
        }


def build_safety_response(analysis: TurnAnalysis) -> str:
    safety = analysis.safety
    resources = _resources()
    support_line = resources.get("psychological_support", "12356")
    police = resources.get("police", "110")
    medical = resources.get("medical_emergency", "120")

    if safety.subject == "第三方":
        if safety.status == SafetyStatus.S4:
            return (
                "风险主体是你提到的那个人，不是你本人。"
                f"现在联系对方所在地的 {police}/{medical}，并说明对方的位置和紧急情况；"
                "同时联系当地能实际到场的家人、室友或工作人员接手陪伴。"
                "仅在自身安全前提下保持电话或消息连接，不要独自前往或独自处置。"
                "你只需回复“已联系紧急服务”或“到场人员已接手”。"
            )
        if safety.status == SafetyStatus.S2:
            return (
                "风险主体是你提到的那个人，不是你本人；这条信息仍需要认真处理。先联系能实际到场的室友、辅导员或家人，"
                "同时保持电话或消息连接，不要让你独自承担。现在只确认一点：你此刻还能联系到对方吗？"
            )
        if safety.has_plan_or_means is None:
            return (
                "对方当前相关想法仍在，现实人员需要尽快到场。请保持联系，并让能到场的人完成下一项确认；"
                "本轮只问一个关键点：对方是否已经有具体计划，或身边有可立即使用的东西？"
            )
        return (
            f"现实人员已经接上后，仍要由他们持续陪伴并联系 {support_line} 或校内专业支持；当前想法仍在时不能当作风险清零。"
            f"若出现计划、可用手段、无法保证安全或突然失联，请立即联系 {police}/{medical}。你不需要继续独自承担。"
        )

    if safety.harm_target == "他伤":
        if safety.status == SafetyStatus.S4:
            return (
                "现在先停止接触对方，保持现实距离，不要前往对方所在地。"
                f"请联系 {police}，明确告知存在他伤风险；若已有伤者，再联系 {medical}。"
                "同时联系能实际到场的可信任者或现场工作人员，让其协助联系现实支持和紧急服务，不独自处置。"
                "你只需回复“已保持距离”“正在联系”或“现实支持已到场”。"
            )
        return (
            "我听到的是对他人的强烈愤怒，这要和自伤语境分开。现在先保持现实距离，不联系或靠近对方；"
            "本轮只确认一点：那句话只是气头上的表达，还是你当前确有伤害对方的打算？"
        )

    if safety.status == SafetyStatus.S4:
        return (
            "现在先停止分析其他问题。不要触碰或携带可能伤害你的东西，立即打开门并到楼道、前台或其他有人值守的位置；"
            f"同时拨打 {medical}，若危险正在发生或无法完成就拨打 {police}，并联系一位能马上到场的人。"
            f"有人陪伴后也可接通 {support_line}。你只需回复“已离开”“正在拨打”或“身边有人”。"
        )

    if safety.status == SafetyStatus.S2:
        evidence = safety.evidence[0] if safety.evidence else "刚才那句话"
        return (
            f"你刚才提到“{evidence}”，我需要先确认它的含义：这是形容你累到想暂时逃开，"
            "还是你现在真的有伤害自己或结束生命的想法？你可以直接回答“只是想逃开”“有这个想法”或“不确定”。"
        )

    if safety.status == SafetyStatus.S3:
        if safety.has_current_thoughts is not True:
            return (
                "谢谢你直接说出来。现在先不分析其他问题，只确认一个安全关键点："
                "这个伤害自己或结束生命的想法，此刻正在发生吗？你可以回答“是”“不是”或“不确定”。"
            )
        if safety.has_plan_or_means is None:
            return (
                "我听清楚了：当前相关想法确实存在，所以继续按 S3 确认。"
                "本轮只问一个关键点：你是否已有具体计划，或身边有可以立即使用来伤害自己的东西？无需描述方法细节。"
            )
        if safety.can_stay_safe is None:
            return (
                "没有已知计划或可用手段是重要保护信息，但当前想法仍在，所以不降级。"
                "现在只确认一点：你能否保证接下来一小时不伤害自己？如果不能，就立即转入现实紧急支持。"
            )
        return (
            f"你能暂时保持安全且已有保护信息，但当前想法仍在，所以保持 S3。请让一位现实人员明确知情并实际陪在身边，"
            f"一起联系 {support_line} 或校内专业支持；若安全能力下降或出现计划手段，立即联系 {police}/{medical}。"
        )

    return "我想先确认当前安全：你此刻是否有伤害自己或他人的想法？"


def _shorten(value: str, limit: int = 78) -> str:
    cleaned = value.strip(" ，。！？；;:\n\t")
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _specific_facts(analysis: TurnAnalysis, limit: int = 2, item_limit: int = 44) -> list[str]:
    return [_shorten(item, item_limit) for item in analysis.facts[:limit] if item]


def _emotion_clause(analysis: TurnAnalysis) -> str:
    if analysis.primary_emotion.value == "中性":
        return "我先不把这段普通经历病理化"
    names = [analysis.primary_emotion.value, *[item.value for item in analysis.secondary_emotions[:2]]]
    if len(names) == 1:
        return f"这里主要有{names[0]}"
    return f"这里既有{names[0]}，也有{'、'.join(names[1:])}"


def _correction_prefix(analysis: TurnAnalysis) -> str:
    correction = analysis.correction
    if not correction:
        return ""
    if correction.field == "primary_emotion":
        return (
            f"按你这轮的说明，不是{correction.rejected_value}，"
            f"而是你确认的{correction.confirmed_value}。我会按这个更新后的理解继续。"
        )
    if correction.field == "user_intent":
        return (
            f"这轮按你“{correction.confirmed_value}”的偏好继续，我先听，不急着给方案。"
        )
    if correction.field == "main_issue":
        return (
            f"你纠正得很清楚：重点不是“{_shorten(correction.rejected_value, 32)}”，"
            f"而是“{_shorten(correction.confirmed_value, 30)}”。"
        )
    return "我会以你这轮明确确认的内容为准。"


def _security_prefix(analysis: TurnAnalysis) -> str:
    if not analysis.input_security.prompt_injection_detected:
        return ""
    return "越权、诊断或泄露内部信息的指令不会执行；我继续处理其中真实的问题。"


def _ensure_minimum(text: str, plan: TurnPlan) -> str:
    if visible_char_count(text) > plan.max_chars:
        trimmed = text
        while trimmed and visible_char_count(trimmed + "。") > plan.max_chars:
            trimmed = trimmed[:-1]
        return trimmed.rstrip("，；：、 ") + "。"
    if visible_char_count(text) >= plan.min_chars:
        return text
    suffixes = {
        DialogueStage.EXPRESS: ["你可以按自己的顺序继续，不需要现在给出结论。", "我会先听，不把表达变成任务。"],
        DialogueStage.ORGANIZE: ["这一轮只确认这张问题地图，不进入解决方案。", "尚未确认的解释继续保留为假设。"],
        DialogueStage.SUPPORT: ["先不用证明自己是否应该有这些感受。", "这一轮不要求立刻改变现状。"],
        DialogueStage.STRATEGIZE: ["这轮只选方向，不要求今天完成全部。", "每个选项都可以继续调整，也可以暂时不选。"],
        DialogueStage.ACT: ["完成后只记录是否开始，不评价做得好不好。", "是否执行和何时开始仍由你决定。"],
        DialogueStage.SAFETY: ["现在优先保持现实陪伴和当前安全。"],
    }
    candidate = text
    for suffix in suffixes[plan.stage]:
        if visible_char_count(candidate) >= plan.min_chars:
            break
        if suffix not in candidate and visible_char_count(candidate + suffix) <= plan.max_chars:
            candidate += suffix
    if visible_char_count(candidate) < plan.min_chars:
        padding = "本轮先停在这个范围，不继续增加新的任务或结论。"
        if visible_char_count(candidate + padding) <= plan.max_chars:
            candidate += padding
    if visible_char_count(candidate) < plan.min_chars:
        padding = "以上只作为当前轮次的暂定内容，仍以你的确认和实际情况为准。"
        if visible_char_count(candidate + padding) <= plan.max_chars:
            candidate += padding
    return candidate


def _offline_action(analysis: TurnAnalysis) -> ActionPlan:
    context = "；".join([analysis.main_issue, *analysis.facts, *analysis.controllable]).lower()
    if any(word in context for word in ["上传", "文件格式", "pdf", "提交系统"]):
        return ActionPlan(
            action="保留原文件，复制一份内容相同的副本，只改成纯英文短文件名后重新上传",
            when="现在",
            location="当前电脑的提交页面",
            duration_minutes=5,
            success_criterion="记录报错文字是否变化",
            obstacle="同时压缩、重导出或改正文，导致无法判断变量",
            fallback="只完成复制和改名，暂不上传",
        )
    if any(word in context for word in ["考试", "复习", "知识点", "考不好"]):
        return ActionPlan(
            action="列出三个最不确定的知识点，只选一个做两道题并记录卡点",
            when="今晚由用户选一个安静时段",
            location="书桌或自习位置",
            duration_minutes=15,
            success_criterion="写下一个明确卡点，不要求全部做对",
            obstacle="一开始就想补完整套复习计划",
            fallback="缩成五分钟，只列三个知识点",
        )
    if any(word in context for word in ["导师", "论文", "范围", "方法说明", "三张图"]):
        return ActionPlan(
            action="写一条不超过三句的范围确认消息，列出当前理解并询问是否需要补充",
            when="今天先写草稿",
            location="邮件或聊天草稿箱",
            duration_minutes=5,
            success_criterion="交付内容、时间和待确认点各出现一次",
            obstacle="把消息扩写成完整解释或整周计划",
            fallback="只写交付内容和一个确认句，暂不发送",
        )
    if any(word in context for word in ["答辩", "演讲", "汇报", "上台"]):
        return ActionPlan(
            action="把开场第一句写进第一页备注，并私下完整读两遍",
            when="下一次练习时",
            location="安静且可随时停止的位置",
            duration_minutes=5,
            success_criterion="能照着备注读完开场，不评价流利程度",
            obstacle="立刻扩展为整篇讲稿或反复重录",
            fallback="只读一遍 30 秒并停止",
        )
    if any(word in context for word in ["sql", "求职", "笔试", "面试题"]):
        return ActionPlan(
            action="重做一道最近重复卡住的题，并只记录卡住的具体步骤",
            when="明天由用户选择时段",
            location="电脑前",
            duration_minutes=25,
            success_criterion="留下一个可复盘的具体卡点",
            obstacle="扩展成全面改简历或连续刷题",
            fallback="缩成十分钟，只读题并写出第一步",
        )
    if any(word in context for word in ["跑步", "运动", "操场", "五公里"]):
        return ActionPlan(
            action="换好鞋后只步行八分钟，到点立即停止",
            when="用户选定的下一次可用时段",
            location="操场；下雨则楼内走廊",
            duration_minutes=8,
            success_criterion="开始并完成八分钟，不要求配速或距离",
            obstacle="沿用过去五公里标准或临时加量",
            fallback="只走两分钟也算开始",
        )
    if any(word in context for word in ["消息", "沟通", "组长", "朋友", "室友", "父母", "署名"]):
        return ActionPlan(
            action="写一条不超过三句的事实型消息：发生了什么、带来什么影响、希望对方做什么",
            when="今天先写草稿",
            location="聊天草稿箱或备忘录",
            duration_minutes=10,
            success_criterion="三项信息清楚且不评价对方人格",
            obstacle="在情绪中扩写为长篇指责",
            fallback="只列事实和请求两句，暂不发送",
        )

    action = (
        _shorten(analysis.controllable[0], 80)
        if analysis.controllable
        else f"把“{_shorten(analysis.main_issue, 52)}”写成一个只需十分钟的第一步"
    )
    return ActionPlan(
        action=action,
        when="今天由用户选择一个相对安静的时间",
        location="用户觉得容易开始的位置",
        duration_minutes=10,
        success_criterion="只完成第一步并记录卡点",
        obstacle="一开始就想解决全部问题",
        fallback="缩成两分钟或只写一句话",
    )


def _selected_action(option: str) -> ActionPlan:
    concrete = {
        "核实一个关键未知信息": "核实一个关键未知信息：先写出一个待确认的问题和可以询问的人",
        "区分可控和不可控部分": "区分可控和不可控部分：在纸上分两栏，各写一项能做和暂时不能控制的事",
        "做一次范围或边界确认": "做一次范围或边界确认：写下一句需要确认的范围说明，先不发送",
    }
    action = concrete.get(option, re.sub(r"^(?:我)?(?:可以|能够|能|愿意)(?:先)?", "", option))
    return ActionPlan(action=action, when="你方便的时候", location="你选择的位置",
                      duration_minutes=option_duration(option) or 5,
                      success_criterion="只开始这一项并记录一处进展或卡点",
                      obstacle="第一步仍然过大", fallback="缩为两分钟，只记录下一步所需的信息")


def offline_response(
    analysis: TurnAnalysis,
    plan: TurnPlan,
    user_input: str = "",
    turn_index: int = 0,
) -> GeneratedResponse:
    if plan.stage == DialogueStage.SAFETY:
        return GeneratedResponse(response=build_safety_response(analysis))

    correction_prefix = _correction_prefix(analysis)
    security_prefix = _security_prefix(analysis)
    prefix = correction_prefix + security_prefix
    if plan.choice_clarification:
        return GeneratedResponse(response=_ensure_minimum(prefix + plan.choice_clarification, plan))
    action = (_selected_action(plan.selected_option) if plan.selected_option else _offline_action(analysis)) if plan.stage == DialogueStage.ACT else None
    text = compose_strategy_response(
        analysis,
        plan,
        user_input=user_input,
        turn_index=turn_index,
        prefix=prefix,
        action=action,
    )
    response = _ensure_minimum(text, plan)
    if plan.stage == DialogueStage.STRATEGIZE and plan.primary_strategy == "比较方案":
        offered = displayed_options(text)
        if offered and displayed_options(response) != offered:
            # Never turn a length-clipped tail into a different executable
            # option merely because the length helper adds a final period.
            numbered = "；".join(f"{index+1}.{option}" for index, option in enumerate(offered))
            compact = prefix + f"可以比较这些方向：{numbered}。你想先选哪一项？"
            if visible_char_count(compact) <= plan.max_chars:
                response = _ensure_minimum(compact, plan)
            else:
                response = _ensure_minimum(prefix + "本轮内容较多，暂不列出可能被截断的选项。你希望先明确哪一个方向？", plan)
    return GeneratedResponse(response=response, action_plan=action)


def _generation_messages(
    user_input: str,
    history: list[dict],
    analysis: TurnAnalysis,
    state: ConversationState,
    plan: TurnPlan,
) -> list[dict[str, str]]:
    template = (PROMPT_DIR / "response_system_prompt.txt").read_text(encoding="utf-8")
    schema = json.dumps(GeneratedResponse.model_json_schema(), ensure_ascii=False)
    system_prompt = template.replace("{schema}", schema)
    payload = {
        "history": format_history(history),
        "current_input": user_input,
        "analysis": analysis.model_dump(mode="json"),
        "confirmed_state": state.model_dump(mode="json"),
        "turn_plan": plan.model_dump(mode="json"),
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def generate_candidate(
    user_input: str,
    history: list[dict],
    analysis: TurnAnalysis,
    state: ConversationState,
    plan: TurnPlan,
    gateway: LLMGateway | None = None,
) -> tuple[GeneratedResponse, GeneratedResponse, bool, str | None]:
    fallback = offline_response(analysis, plan, user_input, state.turn_index)
    if plan.selected_option or plan.choice_clarification:
        return fallback, fallback, False, None
    if plan.stage == DialogueStage.SAFETY or not is_llm_configured(gateway):
        code = None if plan.stage == DialogueStage.SAFETY else "missing_api_key"
        return fallback, fallback, True, code

    try:
        data = call_json(
            gateway=gateway,
            messages=_generation_messages(user_input, history, analysis, state, plan),
            temperature=RESPONSE_TEMPERATURE,
            max_tokens=RESPONSE_MAX_TOKENS,
        )
        generated = GeneratedResponse.model_validate(data)
        return generated, fallback, False, None
    except Exception as exc:
        code = exc.code if isinstance(exc, LLMServiceError) else "generation_invalid"
        return fallback, fallback, True, code
