"""Synthetic O-02 regressions over the real offline process_message chain.

The selected action must be grounded in the ordered options actually shown in
this conversation. No analyzer, generator, composer, or choice state is mocked.
"""
import re

import pytest

from modules.models import ConversationState, DialogueStage
from modules.pipeline import process_message
from utils.text_utils import count_questions


CHOICE_REQUESTS = (
    "我可以先核对申请截止。我可以先问清报名条件。我可以先整理可用时间。"
    "先比较这三个方向，暂时不决定。",
    "我可以先检查设备电量。我可以先联系活动负责人。我可以先备份报名资料。"
    "先比较这三个方向，暂时不决定。",
)
NUMERALS = {1: "一", 2: "二", 3: "三"}


class Dialogue:
    def __init__(self):
        self.state = ConversationState()
        self.history = []

    def send(self, text, mode="一起想办法"):
        result = process_message(
            text, self.history, self.state, mode,
            selected_strategy_mode="rule", llm_gateway=None,
        )
        self.state = result.state
        self.history.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": result.response,
             "meta": {"stage": result.plan.stage.value}},
        ])
        return result


def displayed_options(response):
    """Read option content from the actual visible numbered response."""
    markers = list(re.finditer(r"(?<!\d)([1-9])[.、．)）]\s*", response))
    options = {}
    for position, marker in enumerate(markers):
        end = markers[position + 1].start() if position + 1 < len(markers) else len(response)
        content = re.split(r"[；;。\n]", response[marker.end():end], maxsplit=1)[0].strip()
        options[int(marker.group(1))] = content
    assert set(options) == {1, 2, 3}, response
    assert all(options.values()), response
    return options


def option_core(option):
    # It is fine for an action to drop the user's introductory "我可以先";
    # the concrete operation and object must still identify the chosen item.
    return re.sub(r"^(?:我)?(?:可以|能够|能|愿意)?(?:先)?", "", option).strip(" ，,：:")


def show_choices(dialogue, text=CHOICE_REQUESTS[0]):
    result = dialogue.send(text)
    assert result.plan.stage == DialogueStage.STRATEGIZE
    assert result.state.action_plan is None
    assert result.provider_used == "offline"
    return result, displayed_options(result.response)


def assert_selected_action(result, selected_option, other_options):
    assert result.plan.stage == DialogueStage.ACT
    card = result.state.action_plan
    assert card is not None
    core = option_core(selected_option)
    assert core in card.action, (selected_option, card.action)
    assert core in result.response, (selected_option, result.response)
    assert card.action in result.response
    assert f"{card.duration_minutes}分钟" in result.response
    for other in other_options:
        other_core = option_core(other)
        if other_core != core:
            assert other_core not in card.action
    assert result.audit.safety_passed
    assert result.audit.question_count <= 1
    assert result.provider_used == "offline"


def assert_clarifies_without_new_action(result, previous_card=None):
    assert result.plan.stage not in {DialogueStage.ACT, DialogueStage.SAFETY}
    if previous_card is None:
        assert result.state.action_plan is None
    else:
        assert result.state.action_plan.model_dump() == previous_card.model_dump()
    assert any(word in result.response for word in ("哪", "确认", "明确", "重新", "重列", "选项"))
    assert count_questions(result.response) <= 1
    assert result.audit.safety_passed


@pytest.mark.parametrize("choice_request", CHOICE_REQUESTS)
@pytest.mark.parametrize("index", [1, 2, 3])
def test_numbered_choice_uses_this_sessions_actual_displayed_option(choice_request, index):
    dialogue = Dialogue()
    _, options = show_choices(dialogue, choice_request)
    result = dialogue.send(f"我选第{NUMERALS[index]}个，可以试试，帮我定一个今晚能开始的小步骤。")
    assert_selected_action(result, options[index], [value for key, value in options.items() if key != index])


def test_different_numbered_choices_do_not_collapse_to_the_same_generic_action():
    actions = []
    for index in (1, 2, 3):
        dialogue = Dialogue()
        _, options = show_choices(dialogue)
        result = dialogue.send(f"我选第{NUMERALS[index]}个，可以试试。")
        assert_selected_action(result, options[index], [value for key, value in options.items() if key != index])
        actions.append(result.state.action_plan.action)
    assert len(set(actions)) == 3


@pytest.mark.parametrize("selection", ["我选第二个，可以试试。", "我选第2个，可以试试。"])
def test_numbered_choice_without_a_displayed_offer_first_requests_clarification(selection):
    result = Dialogue().send(selection)
    assert_clarifies_without_new_action(result)


@pytest.mark.parametrize("selection", ["我选第四个，可以试试。", "我选第9个，可以试试。"])
def test_out_of_range_number_does_not_silently_choose_a_different_option(selection):
    dialogue = Dialogue()
    show_choices(dialogue)
    assert_clarifies_without_new_action(dialogue.send(selection))


@pytest.mark.parametrize("selection", ["我选第二个还是第三个，可以试试。", "就那个吧，可以试试。"])
def test_ambiguous_reference_needs_one_clarification_before_any_action(selection):
    dialogue = Dialogue()
    show_choices(dialogue)
    assert_clarifies_without_new_action(dialogue.send(selection))


def test_an_intervening_ordinary_turn_expires_the_old_numbered_offer():
    dialogue = Dialogue()
    show_choices(dialogue)
    pause = dialogue.send("先别给建议，我现在只想把感受说出来。", "我想先说说")
    assert pause.plan.stage == DialogueStage.EXPRESS
    result = dialogue.send("我选第二个，可以试试。")
    assert_clarifies_without_new_action(result)


def test_safety_interruption_invalidates_the_old_offer_after_safety_clears():
    dialogue = Dialogue()
    show_choices(dialogue)
    safety = dialogue.send("我真想永远别醒了。", "我想先说说")
    assert safety.plan.stage == DialogueStage.SAFETY
    assert safety.provider_used == "local_safety"
    clear = dialogue.send("没有这个想法，只是想逃开。我现在只想先说说。", "我想先说说")
    assert clear.plan.stage != DialogueStage.SAFETY
    result = dialogue.send("我选第二个，可以试试。")
    assert_clarifies_without_new_action(result)


def test_a_new_offer_replaces_old_number_to_action_meaning():
    dialogue = Dialogue()
    _, old_options = show_choices(dialogue, CHOICE_REQUESTS[0])
    _, new_options = show_choices(dialogue, CHOICE_REQUESTS[1])
    assert option_core(old_options[2]) != option_core(new_options[2])
    result = dialogue.send("我选第二个，可以试试。")
    assert_selected_action(result, new_options[2], [old_options[2], new_options[1], new_options[3]])


def test_consumed_offer_cannot_silently_create_a_second_action():
    dialogue = Dialogue()
    _, options = show_choices(dialogue)
    first = dialogue.send("我选第二个，可以试试。")
    assert_selected_action(first, options[2], [options[1], options[3]])
    original_card = first.state.action_plan.model_copy(deep=True)
    repeated = dialogue.send("我选第二个，可以试试。")
    assert_clarifies_without_new_action(repeated, original_card)


def test_numbered_history_alone_is_not_an_offer_owned_by_a_new_session():
    other = Dialogue()
    show_choices(other)
    result = process_message(
        "我选第二个，可以试试。", other.history, ConversationState(),
        "一起想办法", selected_strategy_mode="rule", llm_gateway=None,
    )
    assert_clarifies_without_new_action(result)


@pytest.mark.parametrize("selection", ["我不选第二个。", "这里只是举例：‘我选第二个，可以试试’。"])
def test_negated_or_quoted_selection_does_not_execute_the_option(selection):
    dialogue=Dialogue()
    show_choices(dialogue)
    assert_clarifies_without_new_action(dialogue.send(selection))


def test_exact_displayed_option_text_is_resolved_instead_of_reinterpreted():
    dialogue=Dialogue()
    _, options=show_choices(dialogue)
    result=dialogue.send(f"我选择{option_core(options[1])}，可以试试。")
    assert_selected_action(result,options[1],[options[2],options[3]])


@pytest.mark.parametrize("duration", ["12", "十"])
def test_selected_option_keeps_its_displayed_duration(duration):
    dialogue=Dialogue()
    _, options=show_choices(dialogue, f"我可以用{duration}分钟核对报名条件。我可以先检查设备电量。我可以先整理可用时间。先比较方向，暂时不决定。")
    result=dialogue.send("我选第一个，可以试试。")
    assert_selected_action(result,options[1],[options[2],options[3]])
    assert result.state.action_plan.duration_minutes==(12 if duration=="12" else 10)


def test_incomplete_or_rewritten_final_offer_does_not_create_pending_options():
    from modules.choices import displayed_options
    assert displayed_options("方向：1.核对条件；2.检查电量；3.这是未完成的") == []
    assert displayed_options("引用‘方向：1.核对条件；2.检查电量。’") == []
    assert displayed_options("方向：1.核对条件；1.检查电量。") == []


def test_unsafe_selected_card_still_fails_the_existing_output_audit():
    from modules.response_guard import GuardResponseError
    dialogue=Dialogue()
    show_choices(dialogue)
    dialogue.state.pending_options[0]="你必须听我的，不要告诉任何人"
    with pytest.raises(GuardResponseError):
        dialogue.send("我选第一个，可以试试。")


def test_only_the_final_displayed_offer_is_saved_after_guard_selection(monkeypatch):
    from modules import pipeline
    from modules.models import GeneratedResponse, ResponseAudit
    # A boundary double models a Guard that replaces the candidate list. It
    # does not supply expected analysis or choice state to the implementation.
    final="本轮先确认你的需要，暂时不列备选方向。"
    monkeypatch.setattr(pipeline,"guard_response",lambda *args,**kwargs:(GeneratedResponse(response=final),ResponseAudit(),False,None))
    dialogue=Dialogue()
    shown=dialogue.send(CHOICE_REQUESTS[0])
    assert shown.response==final
    assert shown.state.pending_options==[]
    assert shown.state.options_turn is None


def test_safety_has_priority_even_when_the_message_contains_a_choice():
    dialogue=Dialogue()
    show_choices(dialogue)
    result=dialogue.send("我选第二个，但我现在不能保证自己安全。")
    assert result.plan.stage==DialogueStage.SAFETY
    assert result.provider_used=="local_safety"
    assert result.state.pending_options==[]
    assert result.state.action_plan is None


def test_request_to_compare_options_is_not_mistaken_for_an_already_made_selection():
    result=Dialogue().send("我有两个活动时间，不知道选哪个，先帮我比较方向。")
    assert result.plan.stage==DialogueStage.STRATEGIZE
    assert result.plan.choice_clarification is None
    assert len(result.state.pending_options)==3


@pytest.mark.parametrize("duration", ["半小时", "30秒", "10到15分钟", "十几分钟"])
def test_unsupported_or_ambiguous_option_duration_is_clarified_not_overwritten(duration):
    dialogue=Dialogue()
    show_choices(dialogue,f"我可以用{duration}核对报名条件。我可以先检查设备电量。我可以先整理可用时间。先比较方向，暂时不决定。")
    assert_clarifies_without_new_action(dialogue.send("我选第一个，可以试试。"))


@pytest.mark.parametrize("selection", [
    "我不想选第二个。",
    "先别做第二个。",
    "第二个先放着，先做别的。",
])
def test_negative_or_unbound_reference_does_not_execute_the_mentioned_option(selection):
    dialogue = Dialogue()
    show_choices(dialogue)
    assert_clarifies_without_new_action(dialogue.send(selection))


def test_a_quoted_operation_is_not_an_exact_positive_selection():
    dialogue = Dialogue()
    _, options = show_choices(dialogue)
    text = f"我选择暂不行动，只是引用‘{option_core(options[1])}’。"
    assert_clarifies_without_new_action(dialogue.send(text))
