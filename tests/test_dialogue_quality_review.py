"""Synthetic DQ-R1/R2/R3 regressions, not a blind or clinical evaluation.

Real offline analysis, planning, choice state, and selected-action generation
are exercised. Only explicitly labelled final-text boundary tests use a local
Guard-result double to supply punctuation that offline templates do not emit.
"""
import pytest

from modules.choices import displayed_options, option_duration, resolve_choice
from modules.models import ConversationState, DialogueStage, GeneratedResponse, ResponseAudit
from modules.pipeline import process_message


REQUEST = (
    "我可以先核对报名条件。我可以先检查设备电量。我可以先整理可用时间。"
    "先比较方向，暂时不决定。"
)


class Dialogue:
    def __init__(self):
        self.state = ConversationState()
        self.history = []

    def send(self, text):
        result = process_message(
            text, self.history, self.state, "一起想办法",
            selected_strategy_mode="rule", llm_gateway=None,
        )
        self.state = result.state
        self.history.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": result.response,
             "meta": {"stage": result.plan.stage.value}},
        ])
        assert result.provider_used == "offline"
        return result


def offered(text=REQUEST):
    dialogue = Dialogue()
    shown = dialogue.send(text)
    assert shown.plan.stage == DialogueStage.STRATEGIZE
    assert len(shown.state.pending_options) == 3
    assert all(option in shown.response for option in shown.state.pending_options)
    assert shown.state.action_plan is None
    return dialogue, shown


def assert_clarifies(result):
    assert result.plan.stage == DialogueStage.ORGANIZE
    assert result.plan.choice_clarification
    assert result.plan.selected_option is None
    assert result.state.action_plan is None
    assert result.state.current_stage == DialogueStage.ORGANIZE
    assert "本轮小行动" not in result.response
    assert result.audit.safety_passed
    assert result.audit.question_count <= 1


NEGATED = ["我没有选第二个。", "我没选第二个。", "我并没有选择第二个。"]


@pytest.mark.parametrize("text", NEGATED)
def test_r1_resolver_binds_past_negation_to_selection_verb(text):
    dialogue, _ = offered()
    assert resolve_choice(text, dialogue.state) == (True, None)


@pytest.mark.parametrize("text", NEGATED)
def test_r1_real_two_turn_negation_never_generates_second_option_card(text):
    dialogue, shown = offered()
    assert "检查设备电量" in shown.state.pending_options[1]
    result = dialogue.send(text)
    assert_clarifies(result)
    assert result.state.turn_index == 2
    assert "检查设备电量" not in result.response


def test_r1_positive_selection_still_resolves_and_acts_on_actual_second_option():
    dialogue, shown = offered()
    second = shown.state.pending_options[1]
    assert resolve_choice("我选第二个。", dialogue.state) == (True, second)
    result = dialogue.send("我选第二个。")
    assert result.plan.stage == DialogueStage.ACT
    assert result.plan.selected_option == second
    card = result.state.action_plan
    assert card is not None
    assert "检查设备电量" in card.action
    assert "核对报名条件" not in card.action
    assert card.action in result.response
    assert f"{card.duration_minutes}分钟" in result.response


def qualified_list(separator, position):
    qualified = f"先写一封邮件{separator}只存草稿，不要发送"
    first, second = (qualified, "核对报名条件") if position == 1 else ("核对报名条件", qualified)
    return f"可以比较：\n1.{first}；\n2.{second}。\n你想先选哪一项？"


@pytest.mark.parametrize("position", [1, 2])
@pytest.mark.parametrize("separator", ["。", "；"])
def test_r2_raw_multiclause_option_is_not_registered_after_losing_qualifier(separator, position):
    # The expectation is grounded in the literal final text, not a second call
    # to the parser under test. Conservative rejection is the chosen contract.
    final = qualified_list(separator, position)
    assert "只存草稿，不要发送" in final
    assert displayed_options(final) == []


@pytest.mark.parametrize("position", [1, 2])
@pytest.mark.parametrize("separator", ["。", "；"])
def test_r2_final_guard_text_boundary_rejects_ambiguous_offer_before_real_selection(monkeypatch, separator, position):
    from modules import pipeline

    final = qualified_list(separator, position)
    dialogue = Dialogue()
    # Local final-Guard boundary double only; choice parsing, registration,
    # state and the entire second process_message call remain real/unmocked.
    with monkeypatch.context() as boundary:
        boundary.setattr(pipeline, "guard_response", lambda *args, **kwargs: (
            GeneratedResponse(response=final), ResponseAudit(), False, None,
        ))
        shown = dialogue.send(REQUEST)
    assert shown.response == final
    assert shown.plan.stage == DialogueStage.STRATEGIZE
    assert "只存草稿，不要发送" in shown.response
    assert shown.state.pending_options == []
    assert shown.state.options_turn is None
    selection = f"我选第{position}个。"
    assert resolve_choice(selection, shown.state) == (True, None)
    assert_clarifies(dialogue.send(selection))


@pytest.mark.parametrize("tail", ["你想先选哪一项？", "每项都可以调整，也可以暂时不选。"])
def test_r2_complete_single_clause_list_excludes_trailing_question_or_explanation(tail):
    final = f"可以比较：\n1.先写一封邮件；\n2.核对报名条件。\n{tail}"
    assert displayed_options(final) == ["先写一封邮件", "核对报名条件"]


@pytest.mark.parametrize("duration", ["1.5分钟", "两分半钟"])
def test_r3_explicit_unsupported_time_is_not_a_tail_match_or_default(duration):
    assert option_duration(f"用{duration}核对报名条件") is None


def duration_offer(duration):
    return offered(
        f"我可以用{duration}核对报名条件。我可以先检查设备电量。"
        "我可以先整理可用时间。先比较方向，暂时不决定。"
    )


@pytest.mark.parametrize("duration", ["1.5分钟", "两分半钟"])
def test_r3_resolver_rejects_unsupported_duration_from_a_real_displayed_offer(duration):
    dialogue, shown = duration_offer(duration)
    assert f"用{duration}核对报名条件" in shown.response
    assert duration in shown.state.pending_options[0]
    assert resolve_choice("我选第一个。", dialogue.state) == (True, None)


@pytest.mark.parametrize("duration", ["1.5分钟", "两分半钟"])
def test_r3_actual_selection_clarifies_without_mismatched_duration_card(duration):
    dialogue, shown = duration_offer(duration)
    assert f"用{duration}核对报名条件" in shown.response
    result = dialogue.send("我选第一个。")
    assert_clarifies(result)
    assert "用5分钟" not in result.response


@pytest.mark.parametrize("option, expected", [
    ("核对报名条件", 5),
    ("用12分钟核对报名条件", 12),
    ("用十分钟核对报名条件", 10),
    ("用半小时核对报名条件", None),
    ("用30秒核对报名条件", None),
    ("用10到15分钟核对报名条件", None),
    ("用十几分钟核对报名条件", None),
])
def test_r3_existing_duration_contract_is_preserved(option, expected):
    assert option_duration(option) == expected


@pytest.mark.parametrize("duration, expected", [("12分钟", 12), ("十分钟", 10)])
def test_r3_supported_duration_survives_resolver_body_and_card(duration, expected):
    dialogue, shown = duration_offer(duration)
    selected = shown.state.pending_options[0]
    assert resolve_choice("我选第一个。", dialogue.state) == (True, selected)
    result = dialogue.send("我选第一个。")
    assert result.plan.stage == DialogueStage.ACT
    card = result.state.action_plan
    assert card is not None
    assert f"用{duration}核对报名条件" in card.action
    assert card.duration_minutes == expected
    assert card.action in result.response
    assert f"{expected}分钟" in result.response
