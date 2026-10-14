from modules import state_analyzer
from modules.models import ConversationState, Emotion, SafetyStatus, TurnAnalysis
from modules.state_analyzer import analyze_turn


def analyze(text, mode=None):
    result, fallback, error = analyze_turn(text, [], ConversationState(), mode)
    assert fallback is True
    assert error == "missing_api_key"
    return result


def test_positive_exam_sentence_is_not_pressure_only():
    analysis = analyze("考试终于结束了，我很开心。")
    assert analysis.primary_emotion == Emotion.POSITIVE
    assert Emotion.STRESS in analysis.secondary_emotions


def test_old_failed_sadness_cases_are_no_longer_neutral():
    assert analyze("我真的撑不下去了，感觉没有希望。").primary_emotion == Emotion.SADNESS
    assert analyze("我不想活了，感觉活着没有意义。").primary_emotion == Emotion.SADNESS


def test_explicit_mode_overrides_inferred_intent():
    analysis = analyze("最近事情很多。", "我想先说说")
    assert analysis.user_intent.value == "只想倾诉"


def test_crisis_signal_is_separate_from_emotion():
    analysis = analyze("我现在有伤害自己的想法。")
    assert analysis.safety.status == SafetyStatus.S3
    assert analysis.primary_emotion in set(Emotion)


def test_configured_gateway_is_forwarded_to_online_analysis(monkeypatch):
    gateway = object()
    captured_gateways = []

    def fake_call_json(**kwargs):
        captured_gateways.append(kwargs["gateway"])
        return TurnAnalysis(
            main_issue="模型切换测试",
            evidence_spans=["测试模型选择"],
        ).model_dump(mode="json")

    monkeypatch.setattr(state_analyzer, "call_json", fake_call_json)
    result, fallback, error = state_analyzer.analyze_turn(
        "测试模型选择",
        [],
        ConversationState(),
        "我想先说说",
        gateway,
    )

    assert result.main_issue == "模型切换测试"
    assert fallback is False
    assert error is None
    assert captured_gateways == [gateway]


def test_s4_precheck_never_calls_external_gateway(monkeypatch):
    calls = 0

    def unexpected_call(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("S4 text must not be sent to a provider")

    monkeypatch.setattr(state_analyzer, "call_json", unexpected_call)
    result, fallback, error = state_analyzer.analyze_turn(
        "我现在不能保证自己安全。",
        [],
        ConversationState(),
        "先帮我稳一下",
        object(),
    )

    assert result.safety.status == SafetyStatus.S4
    assert fallback is True
    assert error == "local_safety_protocol"
    assert calls == 0
