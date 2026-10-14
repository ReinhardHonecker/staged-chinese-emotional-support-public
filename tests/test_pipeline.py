from modules import pipeline as pipeline_module
from modules import response_generator, response_guard, state_analyzer
from modules.conversation_state import apply_understanding_feedback
from modules.models import (
    ActionPlan,
    ConversationState,
    DialogueStage,
    Emotion,
    GeneratedResponse,
    ResponseAudit,
    UserIntent,
)
from modules.pipeline import UserInputError, process_message
from utils.text_utils import clean_text, truncate_text


def test_empty_input_is_rejected():
    try:
        process_message("   ", [], ConversationState())
    except UserInputError:
        pass
    else:
        raise AssertionError("empty input should fail")


def test_venting_turn_does_not_give_premature_advice():
    result = process_message(
        "别给建议，我今天只想把这件事说出来。",
        [],
        ConversationState(),
        "我想先说说",
    )
    assert result.plan.stage == DialogueStage.EXPRESS
    assert result.plan.advice_allowed is False
    assert result.audit.premature_advice is False
    assert result.audit.question_count <= 1


def test_offline_demo_is_not_reported_as_a_runtime_fallback():
    result = process_message(
        "我今天只想先说说发生了什么。",
        [],
        ConversationState(),
        "我想先说说",
    )

    assert result.mode == "演示模式"
    assert result.provider_used == "offline"
    assert result.model_used == "离线规则"
    assert result.used_fallback is False
    assert result.error_code is None


def test_ambiguous_crisis_uses_controlled_safety_response():
    result = process_message(
        "我真想永远别醒了。", [], ConversationState(), "我想先说说"
    )
    assert result.plan.stage == DialogueStage.SAFETY
    assert "确认" in result.response
    assert "只是想逃开" in result.response
    assert result.audit.question_count <= 1


def test_safety_route_preserves_a_preexisting_ordinary_action_card():
    state = ConversationState(
        action_plan=ActionPlan(
            action="整理明天的课程资料",
            duration_minutes=10,
        )
    )

    result = process_message(
        "我真想永远别醒了。",
        [],
        state,
        "我想先说说",
    )

    assert result.plan.stage == DialogueStage.SAFETY
    assert result.state.action_plan is not None
    assert result.state.action_plan.model_dump() == state.action_plan.model_dump()


def test_immediate_danger_uses_reality_support_resources():
    result = process_message(
        "我现在不能保证自己安全。", [], ConversationState(), "先帮我稳一下"
    )
    assert result.analysis.safety.status.value == "S4"
    assert "12356" in result.response
    assert "110" in result.response
    assert "120" in result.response


def test_s2_s3_and_s4_turns_make_zero_external_calls(monkeypatch):
    calls = 0

    def unexpected_call(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("S2-S4 text must stay local")

    monkeypatch.setattr(state_analyzer, "call_json", unexpected_call)
    monkeypatch.setattr(response_generator, "call_json", unexpected_call)
    monkeypatch.setattr(response_guard, "call_json", unexpected_call)

    for text, expected_status in [
        ("我真想永远别醒了。", "S2"),
        ("我现在有伤害自己的想法。", "S3"),
        ("我现在不能保证自己安全。", "S4"),
    ]:
        result = process_message(
            text,
            [],
            ConversationState(),
            "先帮我稳一下",
            llm_gateway=object(),
        )

        assert result.analysis.safety.status.value == expected_status
        assert result.provider_used == "local_safety"
        assert result.model_used == "固定安全协议"
        assert result.used_fallback is False
        assert result.error_code is None

    assert calls == 0


def test_full_input_safety_scan_precedes_middle_truncation(monkeypatch):
    calls = 0
    crisis_phrase = "我现在不能保证自己安全。"
    raw_input = "甲" * 900 + crisis_phrase + "乙" * 900
    truncated = truncate_text(clean_text(raw_input))
    assert crisis_phrase not in truncated

    def unexpected_call(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("full-input safety text must stay local")

    monkeypatch.setattr(state_analyzer, "call_json", unexpected_call)
    monkeypatch.setattr(response_generator, "call_json", unexpected_call)
    monkeypatch.setattr(response_guard, "call_json", unexpected_call)

    result = process_message(
        raw_input,
        [],
        ConversationState(),
        "我想先说说",
        llm_gateway=object(),
    )

    assert result.analysis.safety.status.value == "S4"
    assert result.analysis.emotion_intensity == 5
    assert result.analysis.input_features["full_input_safety_scan"] is True
    assert result.plan.stage == DialogueStage.SAFETY
    assert result.provider_used == "local_safety"
    assert result.model_used == "固定安全协议"
    assert result.used_fallback is False
    assert result.error_code is None
    assert calls == 0


def test_current_first_person_harm_overrides_mixed_context_locally(monkeypatch):
    calls = 0

    def unexpected_call(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("mixed current-harm text must stay local")

    monkeypatch.setattr(state_analyzer, "call_json", unexpected_call)
    monkeypatch.setattr(response_generator, "call_json", unexpected_call)
    monkeypatch.setattr(response_guard, "call_json", unexpected_call)

    cases = [
        (
            "新闻里在讨论自杀预防，但我现在不能保证自己安全。",
            "S4",
            "本人",
            "自伤",
        ),
        (
            "同学说他不想活了，我现在也有伤害自己的想法。",
            "S3",
            "本人",
            "自伤/结束生命",
        ),
        (
            "新闻里在讨论暴力事件，但我现在想伤害他。",
            "S2",
            "本人",
            "他伤",
        ),
        (
            "同学说他不想活了，我气得想让他去死。",
            "S2",
            "本人",
            "他伤",
        ),
    ]

    for text, expected_status, expected_subject, expected_target in cases:
        result = process_message(
            text,
            [],
            ConversationState(),
            "我想先说说",
            llm_gateway=object(),
        )
        assert result.analysis.safety.status.value == expected_status
        assert result.analysis.safety.subject == expected_subject
        assert result.analysis.safety.harm_target == expected_target
        assert result.analysis.input_features["mixed_context_safety_override"] is True
        assert result.plan.stage == DialogueStage.SAFETY
        assert result.provider_used == "local_safety"
        assert result.used_fallback is False
        assert result.error_code is None

    assert calls == 0


def test_quoted_current_harm_words_do_not_trigger_mixed_context_override():
    result = process_message(
        "新闻里在讨论“我现在不能保证自己安全”这句话，这不是我的情况。",
        [],
        ConversationState(),
        "我想先说说",
    )

    assert result.analysis.safety.status.value == "S0"
    assert result.plan.stage != DialogueStage.SAFETY
    assert result.analysis.input_features.get("mixed_context_safety_override") is not True


def test_provider_history_with_a_safety_episode_is_fully_withheld():
    history = [
        {"role": "user", "content": "我想先聊聊明天的课程。"},
        {"role": "assistant", "content": "好，我们先看课程。"},
        {"role": "user", "content": "我真想永远别醒了。"},
        {
            "role": "assistant",
            "content": "这是形容你累到想暂时逃开，还是你现在真的有伤害自己或结束生命的想法？",
        },
        {"role": "user", "content": "有这个想法。"},
        {"role": "assistant", "content": "继续按安全路径确认。"},
        {"role": "user", "content": "现在已经缓下来了，可以回到刚才的任务。"},
        {"role": "assistant", "content": "好，我们先回到普通任务。"},
        {"role": "user", "content": "接下来只讨论课程安排。"},
        {"role": "assistant", "content": "我们继续讨论课程。"},
    ]

    assert pipeline_module._provider_history_without_safety_episodes(
        history,
        active_safety=False,
    ) == []
    assert pipeline_module._provider_history_without_safety_episodes(
        history,
        active_safety=True,
    ) == []


def test_provider_history_keeps_an_ordinary_window():
    history = [
        {"role": "user", "content": "我想先聊聊明天的课程。"},
        {"role": "assistant", "content": "好，我们先看课程。"},
        {"role": "user", "content": "接下来只讨论课程安排。"},
        {"role": "assistant", "content": "我们继续讨论课程。"},
    ]

    assert pipeline_module._provider_history_without_safety_episodes(
        history,
        active_safety=False,
    ) == history


def test_safety_metadata_withholds_a_partial_window_without_a_known_text_marker():
    reply = "这个环节已确认。"
    assert not any(marker in reply for marker in pipeline_module._SAFETY_RESPONSE_HISTORY_MARKERS)
    history = [
        {"role": "assistant", "content": reply, "meta": {"stage": "安全"}},
        {"role": "user", "content": "现在只讨论课程。"},
    ]
    assert pipeline_module._provider_history_without_safety_episodes(history, active_safety=False) == []


def test_new_fixed_safety_anchors_withhold_windows_even_without_metadata():
    for reply in (
        "对方当前相关想法仍在，现实人员需要尽快到场。",
        "现在只确认一点：你能否保证接下来一小时不伤害自己？",
    ):
        history = [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "接下来只讨论课程。"},
        ]
        assert pipeline_module._provider_history_without_safety_episodes(history, active_safety=False) == []


def test_provider_history_withholds_a_window_that_starts_mid_safety_episode():
    history = [
        {"role": "user", "content": "有这个想法。"},
        {
            "role": "assistant",
            "content": "我听清楚了，继续按 S3 确认当前安全。",
            "meta": {"stage": "安全"},
        },
        {"role": "user", "content": "现在已经缓下来了，可以回到任务。"},
        {"role": "assistant", "content": "好，我们回到任务。"},
    ]

    assert pipeline_module._provider_history_without_safety_episodes(
        history,
        active_safety=False,
    ) == []


def test_understanding_correction_overrides_model_guess():
    result = process_message("我最近很担心。", [], ConversationState(), "我想先说说")
    corrected = apply_understanding_feedback(
        result.state,
        "不准确",
        primary_emotion="委屈/受挫",
        secondary_emotions=[],
        intent="想被理解",
        corrected_issue="努力没有被看到",
    )
    assert corrected.confirmed_primary_emotion == Emotion.GRIEVANCE
    assert corrected.last_analysis.primary_emotion == Emotion.GRIEVANCE
    assert corrected.confirmed_main_issue == "努力没有被看到"
    assert corrected.problem_map.core_problem == "努力没有被看到"


def test_understanding_feedback_does_not_freeze_the_next_turn():
    first = process_message("我最近很担心。", [], ConversationState(), "我想先说说")
    corrected = apply_understanding_feedback(
        first.state,
        "不准确",
        primary_emotion="委屈/受挫",
        secondary_emotions=[],
        intent="想被理解",
        corrected_issue="努力没有被看到",
    )

    second = process_message(
        "事情已经解决了，我现在很开心，也想一起想想下一步。",
        [],
        corrected,
        "一起想办法",
    )

    assert second.analysis.primary_emotion == Emotion.POSITIVE
    assert second.analysis.primary_emotion != Emotion.GRIEVANCE
    assert second.analysis.user_intent == UserIntent.ADVICE
    assert second.state.confirmed_primary_emotion is None
    assert second.state.confirmed_intent is None
    assert second.state.confirmed_advice_readiness is None


def test_guard_fallback_persists_matching_fallback_action_plan(monkeypatch):
    candidate = GeneratedResponse(
        response="这是后来被检查器拒绝的在线回复。",
        action_plan=ActionPlan(action="被拒绝的在线行动"),
    )
    fallback = GeneratedResponse(
        response="这是最终展示给用户的受控回退回复。",
        action_plan=ActionPlan(action="与回退回复匹配的受控行动"),
    )

    def fake_generate_candidate(*_args, **_kwargs):
        return candidate, fallback, False, None

    def fake_guard_response(*_args, **_kwargs):
        return fallback, ResponseAudit(), True, None

    monkeypatch.setattr(
        pipeline_module, "generate_candidate", fake_generate_candidate
    )
    monkeypatch.setattr(pipeline_module, "guard_response", fake_guard_response)

    result = process_message(
        "帮我写一个今晚能开始的小步骤。",
        [],
        ConversationState(),
        "一起想办法",
    )

    assert result.plan.stage == DialogueStage.ACT
    assert result.response == fallback.response
    assert result.state.action_plan is not None
    assert result.state.action_plan.action == "与回退回复匹配的受控行动"
    assert result.state.action_plan.action != "被拒绝的在线行动"


def test_current_input_is_not_required_in_history():
    result = process_message(
        "我脑子很乱。",
        [{"role": "user", "content": "上一轮内容"}],
        ConversationState(),
        "帮我理清楚",
    )
    assert result.plan.stage == DialogueStage.ORGANIZE
    assert result.state.turn_index == 1
