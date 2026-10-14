import json
from collections import Counter

from config import DATA_DIR, STAGE_LENGTH_LIMITS
from modules.models import ConversationState, DialogueStage, SafetyStatus
from modules.response_generator import offline_response
from modules.response_guard import deterministic_audit
from modules.response_planner import plan_turn
from modules.risk_router import precheck_safety
from modules.stage_controller import choose_stage
from modules.state_analyzer import offline_analysis
from scripts.evaluate_scenarios import _evaluate_mode
from utils.text_utils import count_questions, visible_char_count


EXPECTED_COUNTS = {
    "single_emotion": 10,
    "mixed_emotion": 10,
    "support_intent": 8,
    "stage_transition": 10,
    "negation_quote_context": 8,
    "crisis_language": 8,
    "user_correction": 3,
    "robustness": 3,
}

STAGE_MODE = {
    "表达": "我想先说说",
    "梳理": "帮我理清楚",
    "支持": "先帮我稳一下",
    "协商": "一起想办法",
    "行动": "一起想办法",
    "安全": "我想先说说",
}

REQUIRED_TURN_FIELDS = {
    "user_text",
    "gold_state",
    "response_goal",
    "expected_primary_strategy",
    "acceptable_secondary_strategy",
    "must_include",
    "must_avoid",
    "reference_response",
}

REQUIRED_STATE_FIELDS = {
    "stage",
    "primary_emotion",
    "secondary_emotions",
    "emotion_intensity",
    "user_intent",
    "advice_readiness",
    "main_issue",
    "facts",
    "interpretations",
    "trigger",
    "underlying_needs",
    "evidence_spans",
    "certainty",
    "safety_status",
}


def load_scenarios():
    return json.loads((DATA_DIR / "scenarios.json").read_text(encoding="utf-8"))


def test_scenario_distribution_shape_and_refinement_status():
    scenarios = load_scenarios()
    assert [item["scenario_id"] for item in scenarios] == [
        f"scenario_{index:03d}" for index in range(1, 61)
    ]
    assert Counter(item["category"] for item in scenarios) == Counter(EXPECTED_COUNTS)
    assert all(len(item["turns"]) == 3 for item in scenarios)
    assert all([turn["turn_index"] for turn in item["turns"]] == [1, 2, 3] for item in scenarios)
    assert all(item["review_status"] == "codex_refined" for item in scenarios)
    assert all(item["reviewed_by"] == "Codex" for item in scenarios)
    assert all(item["title"] and item["background"] for item in scenarios)
    assert all(len(item["evaluation_focus"]) == 4 for item in scenarios)


def test_all_turns_have_rich_contract_and_unique_text():
    turns = [turn for scenario in load_scenarios() for turn in scenario["turns"]]
    assert len(turns) == 180
    assert len({turn["user_text"] for turn in turns}) == 180
    assert len({turn["reference_response"] for turn in turns}) == 180
    for turn in turns:
        assert REQUIRED_TURN_FIELDS <= turn.keys()
        state = turn["gold_state"]
        assert REQUIRED_STATE_FIELDS <= state.keys()
        assert state["main_issue"]
        assert state["facts"]
        assert state["underlying_needs"]
        assert state["evidence_spans"]
        assert 1 <= state["emotion_intensity"] <= 5
        assert len(state["secondary_emotions"]) <= 2
        assert turn["response_goal"]
        assert turn["acceptable_secondary_strategy"]
        assert turn["must_include"]
        assert turn["must_avoid"]


def test_gold_reference_responses_pass_mechanical_boundaries():
    for scenario in load_scenarios():
        for turn in scenario["turns"]:
            state = turn["gold_state"]
            minimum, maximum = STAGE_LENGTH_LIMITS[state["stage"]]
            if state["stage"] == "安全" and state["safety_status"] == "S4":
                minimum, maximum = 80, 180
            assert minimum <= visible_char_count(turn["reference_response"]) <= maximum
            assert count_questions(turn["reference_response"]) <= 1


def test_all_three_turn_safety_routes_match_gold():
    for scenario in load_scenarios():
        previous = None
        for turn in scenario["turns"]:
            result = precheck_safety(turn["user_text"], previous)
            assert result.status.value == turn["gold_state"]["safety_status"], (
                scenario["scenario_id"],
                turn["turn_index"],
                result.reason,
            )
            previous = result


def test_explicit_ui_mode_adherence_and_action_cards_match_gold():
    """The gold stage deliberately selects the matching UI preference.

    This verifies that explicit user mode choices are obeyed. It must not be
    interpreted or reported as independent stage-classification accuracy.
    """

    for scenario in load_scenarios():
        state = ConversationState()
        for turn in scenario["turns"]:
            gold = turn["gold_state"]
            selected_mode = STAGE_MODE[gold["stage"]]
            analysis = offline_analysis(turn["user_text"], state, selected_mode)
            stage = choose_stage(analysis, state, selected_mode, turn["user_text"])
            plan = plan_turn(analysis, state, stage)
            generated = offline_response(analysis, plan)
            audit = deterministic_audit(
                generated.response,
                analysis,
                plan,
                generated.action_plan,
                validate_action_plan=True,
            )

            assert stage.value == gold["stage"], (scenario["scenario_id"], turn["turn_index"])
            assert not audit.violations, (scenario["scenario_id"], turn["turn_index"], audit.violations)
            if stage == DialogueStage.ACT:
                assert generated.action_plan is not None
                assert generated.action_plan.location
                assert generated.action_plan.success_criterion
                assert generated.action_plan.fallback
            if analysis.safety.status == SafetyStatus.S4:
                assert "110" in generated.response or "120" in generated.response

            state.current_stage = stage
            state.last_analysis = analysis
            state.turn_index += 1
            if generated.action_plan:
                state.action_plan = generated.action_plan


def test_evaluator_reports_explicit_and_blind_stage_protocols_separately():
    selected = load_scenarios()[:2]
    explicit = _evaluate_mode(
        selected,
        "rule",
        use_expected_ui_mode=True,
    )
    blind = _evaluate_mode(
        selected,
        "rule",
        use_expected_ui_mode=False,
    )

    assert explicit["uses_gold_stage_to_select_ui_mode"] is True
    assert explicit["ui_mode_protocol"] == "expected_stage_mapped_to_ui_mode"
    assert blind["uses_gold_stage_to_select_ui_mode"] is False
    assert blind["ui_mode_protocol"] == "no_ui_mode_hint"
    assert explicit["turn_count"] == blind["turn_count"] == 6
    assert 0.0 <= explicit["stage_accuracy"] <= 1.0
    assert 0.0 <= blind["stage_accuracy"] <= 1.0


def test_special_capability_fields_are_present():
    scenarios = {item["scenario_id"]: item for item in load_scenarios()}
    assert all(turn["gold_state"].get("correction") for turn in scenarios["scenario_055"]["turns"])
    assert all(turn["gold_state"].get("correction") for turn in scenarios["scenario_056"]["turns"])
    assert all(turn["gold_state"].get("correction") for turn in scenarios["scenario_057"]["turns"])
    assert all(
        turn["gold_state"].get("input_security", {}).get("prompt_injection_detected")
        for turn in scenarios["scenario_059"]["turns"]
    )
    assert len(scenarios["scenario_060"]["turns"][0]["user_text"]) >= 500
    assert scenarios["scenario_060"]["turns"][0]["gold_state"]["safety_status"] == "S1"
