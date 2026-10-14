import json
from types import SimpleNamespace

import pytest

from modules import pipeline, response_guard, state_analyzer
from modules.models import ActionPlan, ConversationState, DialogueStage, GeneratedResponse, ResponseAudit
from utils.text_utils import clean_text, truncate_text


def dummy_gateway():
    return SimpleNamespace(config=SimpleNamespace(provider=SimpleNamespace(value="mock"), model="local-test"))


def offline_analyzer(user_input, history, state, selected_mode, gateway):
    return state_analyzer.offline_analysis(user_input, state, selected_mode), False, None


def test_pipeline_passes_current_input_and_retains_candidate_card_after_text_repair(monkeypatch):
    candidate = GeneratedResponse(
        response="你肯定是因为不够努力才会这样。",
        action_plan=ActionPlan(action="列出三个最不确定的知识点", duration_minutes=15),
    )
    fallback = GeneratedResponse(
        response="今晚只整理书桌，限时5分钟。",
        action_plan=ActionPlan(action="整理书桌", duration_minutes=5),
    )
    repaired = "今晚先列出三个最不确定的知识点，限时15分钟，是否继续由你决定。"
    captured = []

    def repair(**kwargs):
        captured.append(json.loads(kwargs["messages"][1]["content"]))
        return {"audit": {}, "final_response": repaired}

    monkeypatch.setattr(pipeline, "analyze_turn", offline_analyzer)
    monkeypatch.setattr(pipeline, "generate_candidate", lambda *a, **kw: (candidate, fallback, False, None))
    monkeypatch.setattr(response_guard, "call_json", repair)
    text = "帮我写一个今晚能开始的小步骤。"
    result = pipeline.process_message(text, [], ConversationState(), "一起想办法", llm_gateway=dummy_gateway())
    assert len(captured) == 1
    assert captured[0]["current_input"] == text
    assert result.response == repaired
    assert result.plan.stage == DialogueStage.ACT
    assert result.state.action_plan == candidate.action_plan
    assert result.state.action_plan != fallback.action_plan
    assert result.used_fallback is False


@pytest.mark.parametrize("guard_fallback", [True, False])
def test_pipeline_uses_guard_returned_card_instead_of_inferring_from_flag(guard_fallback, monkeypatch):
    candidate = GeneratedResponse(response="候选正文", action_plan=ActionPlan(action="候选卡"))
    fallback = GeneratedResponse(response="回退正文", action_plan=ActionPlan(action="回退卡"))
    selected = GeneratedResponse(response="Guard 已选正文", action_plan=ActionPlan(action="Guard 最终选择的卡"))
    captured_input = []

    def select(*args, **kwargs):
        captured_input.append(kwargs["user_input"])
        return selected, ResponseAudit(), guard_fallback, None

    monkeypatch.setattr(pipeline, "generate_candidate", lambda *a, **kw: (candidate, fallback, False, None))
    monkeypatch.setattr(pipeline, "guard_response", select)
    text = "帮我写一个今晚能开始的小步骤。"
    result = pipeline.process_message(text, [], ConversationState(), "一起想办法")
    assert captured_input == [text]
    assert result.response == selected.response
    assert result.state.action_plan == selected.action_plan


def test_full_cleaned_input_is_scanned_before_truncation_is_executed(monkeypatch):
    raw = "甲" * 900 + "我现在不能保证自己安全。" + "乙" * 900
    events = []
    original_scan = pipeline.precheck_safety
    original_truncate = pipeline.truncate_text

    def scan(text, previous=None):
        if text == clean_text(raw):
            events.append("scan-full")
        return original_scan(text, previous)

    def truncate(text):
        assert events and events[0] == "scan-full"
        events.append("truncate")
        return original_truncate(text)

    monkeypatch.setattr(pipeline, "precheck_safety", scan)
    monkeypatch.setattr(pipeline, "truncate_text", truncate)
    result = pipeline.process_message(raw, [], ConversationState(), "我想先说说", llm_gateway=object())
    assert events[:2] == ["scan-full", "truncate"]
    assert result.analysis.safety.status.value == "S4"
    assert result.provider_used == "local_safety"


def test_only_bounded_current_input_reaches_ordinary_provider_stages_and_guard(monkeypatch):
    raw = "我想聊聊明天的课程安排。" + "课程资料" * 400
    expected = truncate_text(clean_text(raw))
    seen = {}
    generated = GeneratedResponse(response="我先听你说课程安排。")

    def analyze(text, history, state, mode, gateway):
        seen["analysis"] = text
        return offline_analyzer(text, history, state, mode, gateway)

    def generate(text, *args, **kwargs):
        seen["generation"] = text
        return generated, generated, False, None

    def audit(*args, **kwargs):
        seen["guard"] = kwargs["user_input"]
        return generated, ResponseAudit(), False, None

    monkeypatch.setattr(pipeline, "analyze_turn", analyze)
    monkeypatch.setattr(pipeline, "generate_candidate", generate)
    monkeypatch.setattr(pipeline, "guard_response", audit)
    pipeline.process_message(raw, [], ConversationState(), "我想先说说", llm_gateway=dummy_gateway())
    assert expected != clean_text(raw)
    assert seen == {"analysis": expected, "generation": expected, "guard": expected}


def test_new_other_harm_s4_response_cannot_leak_through_a_partial_provider_history(monkeypatch):
    first = pipeline.process_message("我气得想让他去死。", [], ConversationState(), "我想先说说", llm_gateway=object())
    second = pipeline.process_message("我现在控制不住自己。", [], first.state, "我想先说说", llm_gateway=object())
    assert first.analysis.safety.status.value == "S2"
    assert second.analysis.safety.status.value == "S4"
    assert second.analysis.safety.harm_target == "他伤"
    history = [
        {"role": "assistant", "content": second.response},
        {"role": "user", "content": "事情已经处理好了，我们聊课程。"},
        {"role": "assistant", "content": "我们回到课程。"},
    ]
    assert pipeline._provider_history_without_safety_episodes(history, active_safety=False) == []
    seen = {}
    generated = GeneratedResponse(response="我先听你说课程安排。")

    def analyze(text, provider_history, state, mode, gateway):
        seen["analysis_history"] = provider_history
        return offline_analyzer(text, provider_history, state, mode, gateway)

    def generate(text, provider_history, *args, **kwargs):
        seen["generation_history"] = provider_history
        return generated, generated, False, None

    monkeypatch.setattr(pipeline, "analyze_turn", analyze)
    monkeypatch.setattr(pipeline, "generate_candidate", generate)
    monkeypatch.setattr(pipeline, "guard_response", lambda *a, **kw: (generated, ResponseAudit(), False, None))
    result = pipeline.process_message("接下来只讨论课程安排。", history, ConversationState(), "我想先说说", llm_gateway=dummy_gateway())
    assert result.plan.stage != DialogueStage.SAFETY
    assert seen == {"analysis_history": [], "generation_history": []}


@pytest.mark.parametrize("safety_metadata", [False, True])
def test_provider_bound_stages_receive_only_role_content_after_local_metadata_filtering(monkeypatch, safety_metadata):
    history = [
        {"role": "user", "content": "课程资料已经整理好。", "meta": {"private": "synthetic"}},
        {"role": "assistant", "content": "这个环节已确认。",
         "meta": {"stage": "安全" if safety_metadata else "表达", "provider": "synthetic",
                  "model": "not-for-provider", "latency_ms": 17}},
    ]
    expected = [] if safety_metadata else [{"role": item["role"], "content": item["content"]} for item in history]
    seen = {}
    generated = GeneratedResponse(response="我先听你说课程安排。")

    def analyze(text, provider_history, state, mode, gateway):
        seen["analysis"] = provider_history
        return offline_analyzer(text, provider_history, state, mode, gateway)

    def generate(text, provider_history, *args, **kwargs):
        seen["generation"] = provider_history
        return generated, generated, False, None

    monkeypatch.setattr(pipeline, "analyze_turn", analyze)
    monkeypatch.setattr(pipeline, "generate_candidate", generate)
    monkeypatch.setattr(pipeline, "guard_response", lambda *args, **kwargs: (generated, ResponseAudit(), False, None))
    pipeline.process_message("接下来只讨论课程安排。", history, ConversationState(), "我想先说说", llm_gateway=dummy_gateway())
    assert seen == {"analysis": expected, "generation": expected}
    assert all(set(item) == {"role", "content"} for items in seen.values() for item in items)
