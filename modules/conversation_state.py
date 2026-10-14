from __future__ import annotations

from modules.choices import record_presented_options
from modules.models import (
    ActionPlan,
    AdviceReadiness,
    ConversationState,
    CorrectionSignal,
    DialogueStage,
    Emotion,
    PipelineResult,
    UserIntent,
)


def update_state_from_result(
    state: ConversationState,
    result: PipelineResult | None,
    action_plan: ActionPlan | None = None,
) -> ConversationState:
    if result is None:
        return state
    updated = state.model_copy(deep=True)
    updated.current_stage = result.plan.stage
    updated.last_analysis = result.analysis
    updated.last_strategy = result.plan.primary_strategy
    updated.turn_index += 1
    updated.problem_map.event = result.analysis.trigger
    updated.problem_map.core_problem = result.analysis.main_issue
    updated.problem_map.interpretations = result.analysis.interpretations
    updated.problem_map.emotional_impact = [
        result.analysis.primary_emotion.value,
        *[emotion.value for emotion in result.analysis.secondary_emotions],
    ]
    updated.problem_map.desired_outcome = result.analysis.desired_outcome
    updated.problem_map.controllable = result.analysis.controllable
    updated.problem_map.uncontrollable = result.analysis.uncontrollable
    updated.problem_map.attempts = result.analysis.attempts
    updated.problem_map.resources = result.analysis.resources
    if result.analysis.correction:
        updated.last_correction = result.analysis.correction
        if result.analysis.correction.rejected_value not in updated.rejected_hypotheses:
            updated.rejected_hypotheses.append(result.analysis.correction.rejected_value)

    # Safety temporarily takes priority over ordinary tasks. Keep the previous
    # card in session state; the UI hides it until ordinary support resumes.
    # Only a new ordinary Act result may replace the saved card.
    if result.plan.stage == DialogueStage.ACT and action_plan is not None:
        updated.action_plan = action_plan
    record_presented_options(updated, result.response, result.plan)
    return updated


def apply_understanding_feedback(
    state: ConversationState,
    feedback: str,
    *,
    primary_emotion: str | None = None,
    secondary_emotions: list[str] | None = None,
    intent: str | None = None,
    corrected_issue: str | None = None,
) -> ConversationState:
    updated = state.model_copy(deep=True)
    analysis = updated.last_analysis
    if not analysis:
        return updated

    if feedback == "理解准确":
        updated.confirmed_primary_emotion = analysis.primary_emotion
        updated.confirmed_secondary_emotions = analysis.secondary_emotions
        updated.confirmed_intent = analysis.user_intent
        updated.confirmed_advice_readiness = analysis.advice_readiness
        updated.confirmed_main_issue = analysis.main_issue
        updated.confirmed_needs = analysis.underlying_needs
    else:
        if primary_emotion:
            corrected_emotion = Emotion(primary_emotion)
            old_emotion = analysis.primary_emotion
            updated.confirmed_primary_emotion = corrected_emotion
            analysis.primary_emotion = corrected_emotion
            if old_emotion != corrected_emotion:
                rejected = old_emotion.value
                if rejected not in updated.rejected_hypotheses:
                    updated.rejected_hypotheses.append(rejected)
                updated.last_correction = CorrectionSignal(
                    field="primary_emotion",
                    rejected_value=rejected,
                    confirmed_value=corrected_emotion.value,
                    source="用户在理解校准中修改",
                )
        if secondary_emotions is not None:
            corrected_secondary = [Emotion(item) for item in secondary_emotions]
            updated.confirmed_secondary_emotions = corrected_secondary
            analysis.secondary_emotions = corrected_secondary
        if intent:
            corrected_intent = UserIntent(intent)
            old_intent = analysis.user_intent
            updated.confirmed_intent = corrected_intent
            analysis.user_intent = corrected_intent
            updated.confirmed_advice_readiness = (
                AdviceReadiness.REJECT
                if corrected_intent == UserIntent.VENT
                else analysis.advice_readiness
            )
            analysis.advice_readiness = updated.confirmed_advice_readiness
            if old_intent != corrected_intent:
                rejected = old_intent.value
                if rejected not in updated.rejected_hypotheses:
                    updated.rejected_hypotheses.append(rejected)
                updated.last_correction = CorrectionSignal(
                    field="user_intent",
                    rejected_value=rejected,
                    confirmed_value=corrected_intent.value,
                    source="用户在理解校准中修改",
                )
        if corrected_issue:
            if analysis.main_issue and analysis.main_issue != "尚未明确":
                if analysis.main_issue not in updated.rejected_hypotheses:
                    updated.rejected_hypotheses.append(analysis.main_issue)
            cleaned_issue = corrected_issue.strip()
            old_issue = analysis.main_issue
            updated.confirmed_main_issue = cleaned_issue
            updated.problem_map.core_problem = cleaned_issue
            analysis.main_issue = cleaned_issue
            updated.last_correction = CorrectionSignal(
                field="main_issue",
                rejected_value=old_issue,
                confirmed_value=cleaned_issue,
                source="用户在理解校准中修改",
            )
    updated.last_analysis = analysis
    return updated
