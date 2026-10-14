import pytest

from modules.models import ConversationState, DialogueStage, Emotion
from modules.pipeline import process_message
from modules.response_composer import TEMPLATES, _stable_index, compose_strategy_response
from modules.response_generator import offline_response
from modules.response_guard import deterministic_audit
from utils.text_utils import count_questions, visible_char_count


ORIGINAL = "项目截止是周五，我担心做不完，脑子很乱，帮我区分事实和担心。"
INSUFFICIENT_INFORMATION_MARKERS = (
    "尚未明确",
    "尚未有",
    "尚未说明",
    "尚不清楚",
    "还没有明确",
    "没有明确",
    "没有提供",
    "信息不足",
)


def _normalized(item: str) -> str:
    return item.strip(" ，,。！？!?；;：:\n\t")


def _assert_items_are(items: list[str], expected: list[str]) -> None:
    assert [_normalized(item) for item in items] == expected


def _run_organize(text: str, *, turn_index: int = 0):
    result = process_message(
        text,
        [],
        ConversationState(turn_index=turn_index),
        "帮我理清楚",
        "rule",
        llm_gateway=None,
    )
    assert result.plan.stage == DialogueStage.ORGANIZE
    assert result.plan.primary_strategy == "总结问题地图"
    assert result.response.strip()
    assert result.state.action_plan is None
    assert count_questions(result.response) <= 1
    return result


def _all_map_variants(result, text: str) -> dict[int, str]:
    variants = TEMPLATES["总结问题地图"]
    found: dict[int, str] = {}
    for turn_index in range(128):
        variant_index = _stable_index(
            text,
            turn_index,
            "总结问题地图",
            len(variants),
        )
        response = compose_strategy_response(
            result.analysis,
            result.plan,
            user_input=text,
            turn_index=turn_index,
        )
        found.setdefault(variant_index, response)
        generated = offline_response(result.analysis, result.plan, text, turn_index)
        assert generated.action_plan is None
        assert visible_char_count(generated.response) <= result.plan.max_chars
        audit = deterministic_audit(generated.response, result.analysis, result.plan)
        assert audit.safety_passed
        assert audit.stage_adherence
        assert not audit.premature_advice
    assert set(found) == set(range(len(variants)))
    assert all(count_questions(response) <= 1 for response in found.values())
    return found


def _assert_event_is_explicitly_missing(response: str) -> None:
    assert "事件" in response or "事实" in response
    assert any(marker in response for marker in INSUFFICIENT_INFORMATION_MARKERS)


def test_original_request_separates_event_worry_feeling_and_instruction():
    result = _run_organize(ORIGINAL)
    analysis = result.analysis

    _assert_items_are(analysis.facts, ["项目截止是周五"])
    _assert_items_are(analysis.interpretations, ["我担心做不完"])
    evidence = "｜".join(analysis.evidence_spans)
    assert "脑子很乱" in evidence
    assert "帮我区分事实和担心" in evidence
    assert all("脑子很乱" not in item and "帮我" not in item for item in analysis.facts)
    assert all("脑子很乱" not in item and "帮我" not in item for item in analysis.interpretations)
    assert "担心" not in result.state.problem_map.event
    assert "脑子很乱" not in result.state.problem_map.event
    assert "帮我" not in result.state.problem_map.event

    for response in _all_map_variants(result, ORIGINAL).values():
        assert "项目截止是周五" in response
        assert "担心做不完" in response
        assert "脑子很乱" in response
        assert "事实" in response or "事件" in response
        assert "担忧" in response or "担心" in response or "推测" in response
        assert "感受" in response or "情绪" in response or "状态" in response
        assert "请求" in response or "希望" in response
        assert ORIGINAL not in response


@pytest.mark.parametrize(
    "text",
    [
        "项目截止是周五,我担心做不完,脑子很乱,帮我区分事实和担心。",
        "项目截止是周五。我担心做不完。脑子很乱。帮我区分事实和担心。",
        "项目截止是周五.我担心做不完.脑子很乱.帮我区分事实和担心.",
        "项目截止是周五；我担心做不完；脑子很乱；帮我区分事实和担心。",
        "项目截止是周五;我担心做不完;脑子很乱;帮我区分事实和担心。",
    ],
)
def test_punctuation_variants_keep_the_same_semantic_ownership(text):
    analysis = _run_organize(text).analysis
    _assert_items_are(analysis.facts, ["项目截止是周五"])
    _assert_items_are(analysis.interpretations, ["我担心做不完"])
    assert "脑子很乱" in "｜".join(analysis.evidence_spans)


def test_worry_before_event_does_not_hide_the_later_deadline_fact():
    text = "我担心做不完，项目截止是周五，帮我理清楚。"
    analysis = _run_organize(text).analysis

    _assert_items_are(analysis.facts, ["项目截止是周五"])
    _assert_items_are(analysis.interpretations, ["我担心做不完"])
    assert "帮我理清楚" in "｜".join(analysis.evidence_spans)


def test_worries_without_an_event_do_not_create_a_fact():
    text = "我担心会搞砸，怕别人失望。"
    result = _run_organize(text)

    assert result.analysis.facts == []
    _assert_items_are(result.analysis.interpretations, ["我担心会搞砸", "怕别人失望"])
    assert "担心" not in result.state.problem_map.event or "尚未" in result.state.problem_map.event
    for response in _all_map_variants(result, text).values():
        _assert_event_is_explicitly_missing(response)
        assert "我担心会搞砸" in response
        assert "怕别人失望" in response
        assert not any(
            fragment in response
            for fragment in (
                "已知的是“我担心",
                "事情是“我担心",
                "确认的事实是“我担心",
                "发生了“我担心",
            )
        )


def test_two_events_do_not_create_an_unstated_worry():
    text = "项目截止是周五，我已经完成第一部分。"
    result = _run_organize(text)

    _assert_items_are(result.analysis.facts, ["项目截止是周五", "我已经完成第一部分"])
    assert result.analysis.interpretations == []
    assert any(
        fact in result.state.problem_map.event
        for fact in ("项目截止是周五", "我已经完成第一部分")
    )
    for response in _all_map_variants(result, text).values():
        assert "项目截止是周五" in response
        assert "我已经完成第一部分" in response
        assert "做不完" not in response
        assert "别人失望" not in response


def test_feeling_and_organize_request_do_not_become_event_or_interpretation():
    text = "我脑子很乱，帮我理清楚。"
    result = _run_organize(text)

    assert result.analysis.facts == []
    assert result.analysis.interpretations == []
    evidence = "｜".join(result.analysis.evidence_spans)
    assert "脑子很乱" in evidence
    assert "帮我理清楚" in evidence
    assert "截止" not in result.response
    assert "项目" not in result.response
    assert not any(marker in result.response for marker in ("你并不混乱", "没有混乱", "不是真的乱"))

    for response in _all_map_variants(result, text).values():
        _assert_event_is_explicitly_missing(response)
        assert any(marker in response for marker in INSUFFICIENT_INFORMATION_MARKERS)
        assert not any(
            fragment in response
            for fragment in (
                "已知的是“我脑子很乱",
                "事情是“我脑子很乱",
                "确认的事实是“我脑子很乱",
                "发生了“我脑子很乱",
                "未被证实的是“我脑子很乱",
                "担心或解释是“我脑子很乱",
            )
        )


def test_uncertain_deadline_remains_uncertain():
    text = "项目可能周五截止，我还没有确认。"
    result = _run_organize(text)
    interpretations = "｜".join(result.analysis.interpretations)

    assert "可能" in interpretations
    assert "没有确认" in interpretations
    assert all("项目截止是周五" not in fact for fact in result.analysis.facts)
    assert "项目截止是周五" not in result.response
    assert "可能" in result.response


def test_negated_worry_is_not_turned_into_an_affirmative_worry():
    text = "截止是周五，我不担心做不完，只是想确认交付格式。"
    result = _run_organize(text)
    analysis = result.analysis

    _assert_items_are(analysis.facts, ["截止是周五"])
    for interpretation in analysis.interpretations:
        if "担心做不完" in interpretation:
            assert "不担心做不完" in interpretation
    assert all("交付格式" not in item for item in analysis.facts)
    assert all("交付格式" not in item for item in analysis.interpretations)
    assert "不担心做不完" in "｜".join(analysis.evidence_spans)
    assert analysis.primary_emotion != Emotion.ANXIETY
    for response in _all_map_variants(result, text).values():
        assert "不担心做不完" in response
        assert "你表达的担忧/推测是“我不担心" not in response
        assert "截止是周五" in response


def test_quoted_uncertain_report_keeps_speaker_and_modality():
    text = "老师说：‘项目可能周五截止，我还没有确认。’我脑子很乱，帮我理清楚。"
    result = _run_organize(text)
    owned_claims = [
        item
        for item in [*result.analysis.facts, *result.analysis.interpretations]
        if "周五截止" in item
    ]

    assert owned_claims
    assert all("老师说" in item and "可能" in item and "没有确认" in item for item in owned_claims)
    assert all("我担心" not in item for item in owned_claims)
    assert "项目截止是周五" not in result.response
    assert "老师" in result.response
    assert "可能" in result.response
    if "周五截止" in result.state.problem_map.event:
        assert "老师" in result.state.problem_map.event
        assert "可能" in result.state.problem_map.event


def test_long_report_is_not_shortened_into_an_affirmative_deadline_claim():
    reported = "老师说：‘项目周五截止" + "这条消息还需要与课程工作人员核对" * 20 + "，这个说法不一定准确。’"
    result = _run_organize(reported + "我脑子很乱，帮我理清楚。")
    assert result.analysis.facts == []
    assert any("不一定准确" in item for item in result.analysis.interpretations)
    for response in _all_map_variants(result, reported).values():
        # Keep the entire attributed/qualified claim, or explicitly omit it;
        # an apparently complete quote ending before the qualifier is unsafe.
        if "项目周五截止" in response:
            assert "老师说" in response
            assert "不一定准确" in response
        else:
            assert any(marker in response for marker in ("原文较长", "未展开", "暂不截取"))
        assert visible_char_count(response) <= result.plan.max_chars


def test_reporter_before_a_comma_is_not_detached_from_the_report():
    result = _run_organize("老师说，项目可能周五截止；我不确定，帮我理清楚。")
    assert result.analysis.facts == []
    claims = [item for item in result.analysis.interpretations if "截止" in item]
    assert len(claims) == 1
    assert "老师说" in claims[0] and "可能" in claims[0]
    assert "老师说" in result.response
    assert "可能" in result.response


def test_empty_facts_do_not_erase_the_users_words_in_an_express_turn():
    replies = []
    for text in ("我最近很难过。", "我最近很开心。"):
        result = process_message(text, [], ConversationState(), "我想先说说", llm_gateway=None)
        assert result.analysis.facts == []
        assert result.plan.stage == DialogueStage.EXPRESS
        assert text.rstrip("。") in result.response
        assert "确认的事实" not in result.response
        assert result.audit.safety_passed
        replies.append(result.response)
    assert replies[0] != replies[1]


def test_user_feeling_after_a_quoted_report_keeps_its_own_subject():
    text = "老师说：‘项目可能周五截止，我还没有确认。’但我脑子很乱，帮我理清楚。"
    result = _run_organize(text)
    assert result.analysis.facts == []
    assert all("脑子很乱" not in item for item in result.analysis.interpretations)
    assert "但我脑子很乱" in result.analysis.evidence_spans
    for response in _all_map_variants(result, text).values():
        assert "老师说" in response and "可能" in response and "没有确认" in response
        assert "感受是“但我脑子很乱”" in response


@pytest.mark.parametrize("text", ["我今天被领导批评了。", "我和朋友吵架了。"])
def test_explicit_ordinary_events_remain_user_attributed_events(text):
    result = _run_organize(text)
    assert result.analysis.facts == [text.rstrip("。")]
    assert result.analysis.interpretations == []
    assert text.rstrip("。") in result.response
    assert "你提到" in result.response


def test_unclassified_statement_is_not_lost_or_promoted_to_a_fact():
    text = "我最怕的不是分数难看，是挂科以后爸妈会觉得我没努力。"
    result = _run_organize(text)
    assert result.analysis.facts == []
    for response in _all_map_variants(result, text).values():
        assert "我最怕的不是分数难看" in response
        assert "未表达担忧" not in response
        assert "你尚未单独表达担忧" not in response
        assert any(marker in response for marker in ("待厘清", "待区分", "暂未提取"))
        assert "确认的事实" not in response


R1_EMOTION_CORRECTIONS = [
    ("不是难过，我是生气，帮我理清楚。", Emotion.ANGER, Emotion.SADNESS),
    ("不是焦虑，我是难过，帮我理清楚。", Emotion.SADNESS, Emotion.ANXIETY),
    ("不是焦虑，我是委屈，帮我理清楚。", Emotion.GRIEVANCE, Emotion.ANXIETY),
]


@pytest.mark.parametrize("text,confirmed,rejected", R1_EMOTION_CORRECTIONS)
def test_r1_offline_analysis_applies_explicit_emotion_correction_last(text, confirmed, rejected):
    from modules.state_analyzer import offline_analysis

    analysis = offline_analysis(text, ConversationState(), "帮我理清楚")
    assert analysis.primary_emotion == confirmed
    assert rejected not in [analysis.primary_emotion, *analysis.secondary_emotions]
    assert confirmed not in analysis.secondary_emotions
    assert analysis.correction.field == "primary_emotion"
    assert analysis.correction.confirmed_value == confirmed.value
    assert analysis.correction.rejected_value == rejected.value
    assert all(span in text for span in analysis.evidence_spans)
    assert text.split("，")[0] in analysis.evidence_spans
    assert text.split("，")[1] in analysis.evidence_spans
    assert analysis.suggested_stage == DialogueStage.ORGANIZE


@pytest.mark.parametrize("text,confirmed,rejected", R1_EMOTION_CORRECTIONS)
def test_r1_pipeline_keeps_current_correction_without_locking_the_next_turn(text, confirmed, rejected):
    result = process_message(text, [], ConversationState(), "帮我理清楚", llm_gateway=None)
    assert result.analysis.primary_emotion == confirmed
    assert rejected not in [result.analysis.primary_emotion, *result.analysis.secondary_emotions]
    assert confirmed not in result.analysis.secondary_emotions
    assert result.state.last_analysis == result.analysis
    assert result.state.problem_map.emotional_impact == [
        confirmed.value, *[emotion.value for emotion in result.analysis.secondary_emotions]
    ]
    assert rejected.value not in result.state.problem_map.emotional_impact
    assert result.plan.stage == DialogueStage.ORGANIZE
    assert result.analysis.correction.confirmed_value == confirmed.value
    assert result.state.last_correction == result.analysis.correction
    assert result.state.confirmed_primary_emotion is None
    assert result.provider_used == "offline"
    assert result.state.action_plan is None

    history = [{"role": "user", "content": text}, {"role": "assistant", "content": result.response}]
    following = process_message(
        "事情已经解决了，我现在很开心，也想一起想想下一步。",
        history, result.state, "一起想办法", llm_gateway=None,
    )
    assert following.analysis.primary_emotion == Emotion.POSITIVE
    assert following.analysis.correction is None
    assert following.state.confirmed_primary_emotion is None
    assert following.state.turn_index == 2
