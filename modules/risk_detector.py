"""Compatibility adapter for the former four-level risk API.

The new system exposes non-clinical S0-S4 safety routing states and keeps the
semantic subject/time/polarity fields needed to avoid keyword-only decisions.
"""

from modules.risk_router import precheck_safety


def detect_risk(user_input: str) -> dict:
    signal = precheck_safety(user_input)
    return {
        "safety_status": signal.status.value,
        "subject": signal.subject,
        "time_reference": signal.time_reference,
        "polarity": signal.polarity,
        "harm_target": signal.harm_target,
        "needs_clarification": signal.needs_clarification,
        "reason": signal.reason,
    }
