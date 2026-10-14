from modules.models import (
    AdviceReadiness,
    ConversationState,
    DialogueStage,
    SafetyStatus,
    TurnAnalysis,
    UserIntent,
)


MODE_STAGE = {
    "我想先说说": DialogueStage.EXPRESS,
    "帮我理清楚": DialogueStage.ORGANIZE,
    "一起想办法": DialogueStage.STRATEGIZE,
    "先帮我稳一下": DialogueStage.SUPPORT,
}

ACTION_SELECTION_MARKERS = [
    "我选",
    "就这个",
    "选第二个",
    "选第一个",
    "可以试试",
    "愿意做一个",
    "愿意先做",
    "很小的下一步",
    "先帮我把这条",
    "小步骤",
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

ACTION_REVIEW_MARKERS = ["完成了", "没做", "没完成", "太难", "做起来", "上次定的", "卡住了"]


def choose_stage(
    analysis: TurnAnalysis,
    state: ConversationState,
    selected_mode: str | None,
    user_input: str,
) -> DialogueStage:
    if analysis.safety.status in {SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4}:
        return DialogueStage.SAFETY

    # Current explicit boundaries override the UI selection and model guess.
    if analysis.user_intent == UserIntent.VENT:
        return DialogueStage.EXPRESS
    if analysis.user_intent == UserIntent.CLARIFY:
        return DialogueStage.ORGANIZE
    if analysis.advice_readiness == AdviceReadiness.REJECT:
        return DialogueStage.EXPRESS
    if analysis.user_intent == UserIntent.STABILIZE:
        return DialogueStage.SUPPORT

    action_selected = analysis.suggested_stage == DialogueStage.ACT or (
        analysis.advice_readiness == AdviceReadiness.EXPLICIT
        and any(marker in user_input for marker in ACTION_SELECTION_MARKERS)
    )
    if action_selected and analysis.advice_readiness in {
        AdviceReadiness.WILLING,
        AdviceReadiness.EXPLICIT,
    }:
        return DialogueStage.ACT

    if selected_mode in MODE_STAGE:
        requested = MODE_STAGE[selected_mode]
        if requested == DialogueStage.STRATEGIZE:
            if state.current_stage == DialogueStage.STRATEGIZE and action_selected:
                return DialogueStage.ACT
            return DialogueStage.STRATEGIZE
        return requested

    if state.action_plan and any(word in user_input for word in ACTION_REVIEW_MARKERS):
        return DialogueStage.ACT
    if analysis.user_intent in {UserIntent.ADVICE, UserIntent.CHOOSE}:
        if analysis.advice_readiness in {AdviceReadiness.WILLING, AdviceReadiness.EXPLICIT}:
            return DialogueStage.STRATEGIZE
    if not analysis.facts or analysis.main_issue == "尚未明确":
        return DialogueStage.EXPRESS
    if not analysis.interpretations:
        return DialogueStage.ORGANIZE
    if state.confirmed_primary_emotion is None:
        return DialogueStage.SUPPORT
    return analysis.suggested_stage
