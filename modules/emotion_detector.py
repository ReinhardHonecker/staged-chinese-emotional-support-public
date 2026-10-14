"""Compatibility adapter for the former single-label emotion API.

The application no longer calls this module. New code should use
modules.state_analyzer.analyze_turn so emotion is interpreted together with
intent, cause, stage, and safety context.
"""

from modules.models import ConversationState
from modules.state_analyzer import analyze_turn


def detect_emotion(user_input: str) -> dict:
    analysis, used_fallback, _ = analyze_turn(
        user_input, [], ConversationState(), None
    )
    return {
        "emotion": analysis.primary_emotion.value,
        "secondary_emotions": [item.value for item in analysis.secondary_emotions],
        "intensity": analysis.emotion_intensity,
        "reason": analysis.trigger,
        "certainty": analysis.certainty.value,
        "used_fallback": used_fallback,
    }
