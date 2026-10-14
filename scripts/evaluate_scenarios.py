from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.models import ConversationState
from modules.choices import record_presented_options
from modules.response_generator import offline_response
from modules.response_guard import deterministic_audit
from modules.response_planner import plan_turn
from modules.risk_router import precheck_safety
from modules.stage_controller import choose_stage
from modules.state_analyzer import offline_analysis


STAGE_MODE = {
    "表达": "我想先说说",
    "梳理": "帮我理清楚",
    "支持": "先帮我稳一下",
    "协商": "一起想办法",
    "行动": "一起想办法",
    "安全": "我想先说说",
}


def _evaluate_mode(
    selected: list[dict],
    selector_mode: str,
    *,
    use_expected_ui_mode: bool,
) -> dict:
    """Evaluate one strategy engine under an explicit or blind stage protocol.

    ``use_expected_ui_mode=True`` measures whether the pipeline obeys a user
    preference that is deliberately chosen from the scenario's expected stage.
    It is an interaction-contract test, not an independent stage-classification
    score. ``False`` withholds that hint and reports blind stage routing.
    """

    safety_expected: list[str] = []
    safety_predicted: list[str] = []
    stage_expected: list[str] = []
    stage_predicted: list[str] = []
    safety_mismatches: list[dict] = []
    stage_mismatches: list[dict] = []
    audit_failures: list[dict] = []
    responses: list[str] = []
    strategies: list[str] = []
    sources: list[str] = []
    action_turns = 0
    action_cards = 0

    for scenario in selected:
        state = ConversationState()
        previous_safety = None
        history: list[dict] = []
        for turn in scenario["turns"]:
            gold = turn["gold_state"]
            user_text = turn["user_text"]
            safety = precheck_safety(user_text, previous_safety)
            safety_expected.append(gold["safety_status"])
            safety_predicted.append(safety.status.value)
            if safety.status.value != gold["safety_status"]:
                safety_mismatches.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "turn": turn["turn_index"],
                        "expected": gold["safety_status"],
                        "predicted": safety.status.value,
                        "reason": safety.reason,
                    }
                )
            previous_safety = safety

            selected_mode = STAGE_MODE[gold["stage"]] if use_expected_ui_mode else None
            analysis = offline_analysis(user_text, state, selected_mode)
            stage = choose_stage(analysis, state, selected_mode, user_text)
            plan = plan_turn(
                analysis,
                state,
                stage,
                history=history,
                user_input=user_text,
                selector_mode=selector_mode,
            )
            stage = plan.stage
            generated = offline_response(analysis, plan, user_text, state.turn_index)
            audit = deterministic_audit(
                generated.response,
                analysis,
                plan,
                generated.action_plan,
                validate_action_plan=True,
            )
            responses.append(generated.response)
            strategies.append(plan.primary_strategy)
            sources.append(plan.strategy_source)

            stage_expected.append(gold["stage"])
            stage_predicted.append(stage.value)
            if stage.value != gold["stage"]:
                stage_mismatches.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "turn": turn["turn_index"],
                        "expected": gold["stage"],
                        "predicted": stage.value,
                        "selected_mode": selected_mode,
                        "intent": analysis.user_intent.value,
                        "advice_readiness": analysis.advice_readiness.value,
                    }
                )
            if audit.violations:
                audit_failures.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "turn": turn["turn_index"],
                        "violations": audit.violations,
                    }
                )
            if gold["stage"] == "行动":
                action_turns += 1
                if generated.action_plan is not None:
                    action_cards += 1

            state.current_stage = stage
            state.last_analysis = analysis
            state.last_strategy = plan.primary_strategy
            state.turn_index += 1
            if generated.action_plan:
                state.action_plan = generated.action_plan
            record_presented_options(state, generated.response, plan)
            history.extend(
                [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": generated.response},
                ]
            )

    turn_count = len(safety_expected)
    safety_correct = sum(a == b for a, b in zip(safety_expected, safety_predicted))
    stage_correct = sum(a == b for a, b in zip(stage_expected, stage_predicted))
    return {
        "selector_mode": selector_mode,
        "ui_mode_protocol": (
            "expected_stage_mapped_to_ui_mode" if use_expected_ui_mode else "no_ui_mode_hint"
        ),
        "uses_gold_stage_to_select_ui_mode": use_expected_ui_mode,
        "turn_count": turn_count,
        "safety_route_accuracy": safety_correct / turn_count,
        "stage_accuracy": stage_correct / turn_count,
        "offline_behavior_clean_rate": (turn_count - len(audit_failures)) / turn_count,
        "action_card_coverage_on_expected_action_turns": (
            action_cards / action_turns if action_turns else 1.0
        ),
        "exact_repeated_response_rate": (turn_count - len(set(responses))) / turn_count,
        "strategy_distribution": Counter(strategies),
        "strategy_source_distribution": Counter(sources),
        "expected_safety_distribution": Counter(safety_expected),
        "predicted_safety_distribution": Counter(safety_predicted),
        "expected_stage_distribution": Counter(stage_expected),
        "predicted_stage_distribution": Counter(stage_predicted),
        "safety_mismatches": safety_mismatches,
        "stage_mismatches": stage_mismatches,
        "audit_failures": audit_failures,
    }


def evaluate(include_drafts: bool = False) -> dict:
    scenarios = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))
    selected = [
        item
        for item in scenarios
        if include_drafts or item.get("review_status") in {"codex_refined", "approved"}
    ]
    if not selected:
        raise RuntimeError("没有 codex_refined 或 approved 场景可评测。")

    rule_explicit = _evaluate_mode(
        selected,
        "rule",
        use_expected_ui_mode=True,
    )
    learned_explicit = _evaluate_mode(
        selected,
        "learned",
        use_expected_ui_mode=True,
    )
    blind = _evaluate_mode(
        selected,
        "rule",
        use_expected_ui_mode=False,
    )

    result = {
        "scenario_count": len(selected),
        "review_status": "all_statuses" if include_drafts else "codex_refined_or_approved",
        "evaluation_protocols": {
            "explicit_mode_adherence": {
                "description": (
                    "The expected stage is mapped to a matching UI mode. This measures "
                    "preference adherence and must not be reported as blind stage classification."
                ),
                **rule_explicit,
            },
            "blind_stage_routing": {
                "description": (
                    "No UI mode hint is supplied. This is the independent offline stage-routing result."
                ),
                **blind,
            },
        },
        # Backward-compatible summary keys with protocol names made explicit.
        "safety_route_accuracy": rule_explicit["safety_route_accuracy"],
        "stage_accuracy_with_expected_ui_mode": rule_explicit["stage_accuracy"],
        "stage_accuracy_without_ui_mode": blind["stage_accuracy"],
        "offline_behavior_clean_rate": rule_explicit["offline_behavior_clean_rate"],
        "action_card_coverage": rule_explicit[
            "action_card_coverage_on_expected_action_turns"
        ],
        "exact_repeated_response_rate": rule_explicit["exact_repeated_response_rate"],
        "strategy_distribution": rule_explicit["strategy_distribution"],
        "strategy_source_distribution": rule_explicit["strategy_source_distribution"],
        "expected_safety_distribution": rule_explicit["expected_safety_distribution"],
        "predicted_safety_distribution": rule_explicit["predicted_safety_distribution"],
        "expected_stage_distribution": rule_explicit["expected_stage_distribution"],
        "predicted_stage_distribution_with_expected_ui_mode": rule_explicit[
            "predicted_stage_distribution"
        ],
        "predicted_stage_distribution_without_ui_mode": blind[
            "predicted_stage_distribution"
        ],
        "safety_mismatches": rule_explicit["safety_mismatches"],
        "stage_mismatches_with_expected_ui_mode": rule_explicit["stage_mismatches"],
        "stage_mismatches_without_ui_mode": blind["stage_mismatches"],
        "audit_failures": rule_explicit["audit_failures"],
        "ab_comparison": {
            "protocol": "expected_stage_mapped_to_ui_mode",
            "note": (
                "The strategy A/B comparison holds the explicit UI-mode contract constant; "
                "it does not evaluate blind stage inference."
            ),
            "rule_baseline": {
                key: rule_explicit[key]
                for key in [
                    "offline_behavior_clean_rate",
                    "action_card_coverage_on_expected_action_turns",
                    "exact_repeated_response_rate",
                    "strategy_distribution",
                    "strategy_source_distribution",
                ]
            },
            "learned_experiment": {
                key: learned_explicit[key]
                for key in [
                    "offline_behavior_clean_rate",
                    "action_card_coverage_on_expected_action_turns",
                    "exact_repeated_response_rate",
                    "strategy_distribution",
                    "strategy_source_distribution",
                ]
            },
            "learned_audit_failures": learned_explicit["audit_failures"],
        },
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "评测精修场景，分别报告显式 UI 模式遵循与无模式提示的盲阶段分流，并比较规则与学习策略引擎"
        )
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="兼容参数：同时纳入非 codex_refined/approved 数据",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.include_drafts), ensure_ascii=False, indent=2))
