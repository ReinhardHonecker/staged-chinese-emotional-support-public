import json

import pytest

from modules import strategy_selector
from modules.models import ConversationState, DialogueStage
from modules.response_composer import TEMPLATES, compose_strategy_response
from modules.response_planner import plan_turn
from modules.stage_controller import choose_stage
from modules.state_analyzer import offline_analysis
from modules.strategy_selector import STAGE_STRATEGIES, predict_strategy, rule_prediction
from utils.text_utils import count_questions


def test_all_learned_strategies_have_at_least_four_offline_variants():
    assert len(TEMPLATES) == 13
    assert all(len(variants) >= 4 for variants in TEMPLATES.values())


def test_rule_strategy_is_deterministic_without_classifier_probabilities():
    for stage, allowed in STAGE_STRATEGIES.items():
        prediction = rule_prediction(stage)
        assert prediction.probabilities == {}
        assert prediction.source == "rule"
        assert prediction.decision_basis
        if stage == DialogueStage.SAFETY:
            continue
        assert prediction.primary_strategy in allowed


def test_safety_stage_bypasses_learned_model():
    state = ConversationState()
    analysis = offline_analysis("我真想永远别醒了", state, "我想先说说")
    prediction = predict_strategy(
        "我真想永远别醒了", [], analysis, state, DialogueStage.SAFETY, "learned"
    )
    assert prediction.source == "rule"
    assert prediction.fallback_reason == "safety_stage_bypass"
    assert prediction.probabilities == {}


def test_second_candidate_becomes_auxiliary_only_in_turn_plan():
    user_text = "我想先把这件事情说清楚"
    state = ConversationState()
    analysis = offline_analysis(user_text, state, "我想先说说")
    stage = choose_stage(analysis, state, "我想先说说", user_text)
    prediction = rule_prediction(stage)
    plan = plan_turn(
        analysis,
        state,
        stage,
        user_input=user_text,
        selector_mode="rule",
    )
    assert plan.secondary_strategy == prediction.secondary_candidate
    assert "secondary_candidate" in type(prediction).model_fields
    assert "secondary_strategy" in type(plan).model_fields


def test_unaccepted_model_is_opt_in_and_auto_mode_uses_rule():
    user_text = "我最近一直焦虑，想先听听有哪些处理方向"
    state = ConversationState()
    analysis = offline_analysis(user_text, state, "一起想办法")
    stage = choose_stage(analysis, state, "一起想办法", user_text)

    automatic = predict_strategy(user_text, [], analysis, state, stage, "auto")
    experimental = predict_strategy(user_text, [], analysis, state, stage, "learned")

    assert automatic.source == "rule"
    assert automatic.fallback_reason and automatic.fallback_reason.startswith("model_unavailable")
    assert experimental.source in {"learned_experimental", "rule"}
    if experimental.source == "learned_experimental":
        assert abs(sum(experimental.probabilities.values()) - 1.0) < 1e-9
        assert set(experimental.probabilities) <= set(STAGE_STRATEGIES[stage])
    else:
        assert experimental.probabilities == {}


def test_template_selection_is_reproducible_and_not_single_sentence():
    user_text = "我想把这件事先说清楚"
    state = ConversationState()
    analysis = offline_analysis(user_text, state, "我想先说说")
    plan = plan_turn(
        analysis,
        state,
        DialogueStage.EXPRESS,
        user_input=user_text,
        selector_mode="rule",
    )
    first = compose_strategy_response(
        analysis, plan, user_input=user_text, turn_index=0
    )
    repeated = compose_strategy_response(
        analysis, plan, user_input=user_text, turn_index=0
    )
    variants = {
        compose_strategy_response(analysis, plan, user_input=user_text, turn_index=index)
        for index in range(12)
    }
    assert first == repeated
    assert len(variants) >= 2
    assert count_questions(first) <= 1


def test_checksum_mismatch_prevents_joblib_deserialization(tmp_path, monkeypatch):
    artifact = tmp_path / "strategy_selector.joblib"
    metadata = tmp_path / "strategy_selector_metadata.json"
    artifact.write_bytes(b"reviewed-artifact-placeholder")
    metadata.write_text(
        json.dumps(
            {
                "accepted": False,
                "artifact_size_bytes": artifact.stat().st_size,
                "artifact_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    load_calls = 0

    def unexpected_load(*args, **kwargs):
        nonlocal load_calls
        load_calls += 1
        raise AssertionError("unverified artifacts must never be deserialized")

    monkeypatch.setattr(strategy_selector, "STRATEGY_MODEL_PATH", artifact)
    monkeypatch.setattr(strategy_selector, "STRATEGY_MODEL_META_PATH", metadata)
    monkeypatch.setattr(strategy_selector, "_load_artifact", unexpected_load)
    strategy_selector._verified_metadata.cache_clear()

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        strategy_selector._artifact(allow_unaccepted=True)
    assert load_calls == 0
