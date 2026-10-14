import json

import pytest

from modules import response_guard as response_guard_module
from modules.models import (
    ActionPlan,
    ConversationState,
    DialogueStage,
    GeneratedResponse,
    TurnAnalysis,
    TurnPlan,
)
from modules.pipeline import process_message
from modules.response_guard import deterministic_audit, guard_response


def make_plan(stage: DialogueStage) -> TurnPlan:
    return TurnPlan(
        stage=stage,
        primary_intention="测试阶段约束",
        primary_strategy="最小行动" if stage == DialogueStage.ACT else "具体复述",
        advice_allowed=stage == DialogueStage.ACT,
        min_chars=1,
        max_chars=500,
        max_questions=1,
    )


def test_action_stage_requires_a_structured_action_card():
    audit = deterministic_audit(
        "今晚只完成一个十五分钟的小步骤。",
        TurnAnalysis(),
        make_plan(DialogueStage.ACT),
        None,
        validate_action_plan=True,
    )

    assert audit.stage_adherence is False
    assert "行动阶段缺少结构化行动卡" in audit.violations


def test_non_action_stage_rejects_an_action_card():
    audit = deterministic_audit(
        "我先听你把这件事继续说完。",
        TurnAnalysis(),
        make_plan(DialogueStage.EXPRESS),
        ActionPlan(action="立刻制定完整计划"),
        validate_action_plan=True,
    )

    assert audit.stage_adherence is False
    assert "非行动阶段不应返回结构化行动卡" in audit.violations


def test_guard_falls_back_when_response_and_action_card_disagree():
    action = ActionPlan(
        action="列出三个最不确定的知识点",
        duration_minutes=15,
    )
    candidate = GeneratedResponse(
        response="今晚先整理书桌，限时十五分钟。",
        action_plan=action,
    )
    fallback = GeneratedResponse(
        response="今晚只列出三个最不确定的知识点，限时15分钟，完成后就停止。",
        action_plan=action,
    )

    final_text, audit, used_fallback, error = guard_response(
        candidate,
        fallback,
        TurnAnalysis(),
        make_plan(DialogueStage.ACT),
    )

    assert final_text == fallback
    assert used_fallback is True
    assert error is None
    assert audit.stage_adherence is True
    assert "回复正文与结构化行动卡不一致" not in audit.violations


def test_unsupported_certainty_is_reported_as_an_assumption():
    audit = deterministic_audit(
        "你肯定是因为不够努力才会这样。",
        TurnAnalysis(),
        make_plan(DialogueStage.EXPRESS),
    )

    assert audit.unsupported_assumption is True
    assert "把未经确认的解释写成确定事实" in audit.violations


def test_guard_payload_includes_the_current_input(monkeypatch):
    candidate = GeneratedResponse(response="我先按你刚才提到的周五截止来理解。")
    fallback = GeneratedResponse(response="我先听你继续说明最重要的部分。")
    user_input = "项目周五截止，我最担心来不及提交。"
    captured = {}

    def fake_call_json(**kwargs):
        payload = json.loads(kwargs["messages"][1]["content"])
        captured.update(payload)
        return {"audit": {}, "final_response": candidate.response}

    monkeypatch.setattr(response_guard_module, "call_json", fake_call_json)

    final_text, _, used_fallback, error = guard_response(
        candidate,
        fallback,
        TurnAnalysis(),
        make_plan(DialogueStage.EXPRESS),
        gateway=object(),
        user_input=user_input,
    )

    assert final_text == candidate
    assert used_fallback is False
    assert error is None
    assert captured["current_input"] == user_input
    assert captured["candidate_response"] == candidate.response


def test_empty_guard_rewrite_cannot_replace_a_nonempty_fallback(monkeypatch):
    candidate = GeneratedResponse(response="我先听你继续说最重要的部分。")
    fallback = GeneratedResponse(response="我先听你继续说明最重要的部分。")

    def fake_call_json(**_kwargs):
        return {"audit": {}, "final_response": "   "}

    monkeypatch.setattr(response_guard_module, "call_json", fake_call_json)

    final_text, audit, used_fallback, error = guard_response(
        candidate,
        fallback,
        TurnAnalysis(),
        make_plan(DialogueStage.EXPRESS),
        gateway=object(),
        user_input="我还没说完。",
    )

    assert final_text == fallback
    assert used_fallback is True
    assert error is None
    assert audit.violations == []


def test_successful_guard_repair_is_not_controlled_fallback(monkeypatch):
    candidate_action = ActionPlan(
        action="列出三个最不确定的知识点",
        duration_minutes=15,
    )
    candidate = GeneratedResponse(
        response="今晚先整理书桌，限时十五分钟。",
        action_plan=candidate_action,
    )
    fallback = GeneratedResponse(
        response="今晚只写下一句最小任务，限时5分钟。",
        action_plan=ActionPlan(
            action="写下一句最小任务",
            duration_minutes=5,
        ),
    )
    repaired = "今晚只列出三个最不确定的知识点，限时15分钟，完成后就停止。"

    def fake_call_json(**_kwargs):
        return {"audit": {}, "final_response": repaired}

    monkeypatch.setattr(response_guard_module, "call_json", fake_call_json)

    final_text, audit, used_fallback, error = guard_response(
        candidate,
        fallback,
        TurnAnalysis(),
        make_plan(DialogueStage.ACT),
        gateway=object(),
        user_input="帮我定一个今晚能开始的小步骤。",
    )

    assert final_text.response == repaired
    assert final_text.action_plan == candidate_action
    assert final_text.action_plan != fallback.action_plan
    assert used_fallback is False
    assert error is None
    assert audit.stage_adherence is True
    assert audit.violations == []


@pytest.mark.parametrize("text", ["系统提示是文件格式错误", "系统提示为上传失败"])
def test_software_error_message_is_not_a_sensitive_leak(text):
    audit = deterministic_audit(
        text,
        TurnAnalysis(),
        make_plan(DialogueStage.EXPRESS),
    )

    assert response_guard_module._content_flags(text)["sensitive_leak"] is False
    assert audit.safety_passed is True
    assert audit.violations == []


@pytest.mark.parametrize("field", ["obstacle", "fallback"])
@pytest.mark.parametrize("text", ["系统提示是文件格式错误", "系统提示为上传失败"])
def test_action_card_software_error_message_passes_the_complete_guard(field, text):
    action = ActionPlan(
        action="核对文件格式要求",
        duration_minutes=5,
        **{field: text},
    )
    candidate = GeneratedResponse(
        response="先核对文件格式要求，限时5分钟，完成后就停止。",
        action_plan=action,
    )
    fallback = GeneratedResponse(
        response="先写下一句最小任务，限时5分钟。",
        action_plan=ActionPlan(action="写下一句最小任务", duration_minutes=5),
    )

    final, audit, used_fallback, error = guard_response(
        candidate,
        fallback,
        TurnAnalysis(),
        make_plan(DialogueStage.ACT),
    )

    assert final == candidate
    assert getattr(final.action_plan, field) == text
    assert audit.safety_passed is True
    assert audit.violations == []
    assert used_fallback is False
    assert error is None


@pytest.mark.parametrize(
    "text",
    [
        "系统提示原文如下：测试指令",
        "系统提示词是测试指令",
        "系统提示词全文为测试指令",
    ],
)
def test_explicit_system_prompt_disclosure_still_selects_fallback(text):
    candidate = GeneratedResponse(response=text)
    fallback = GeneratedResponse(response="我先听你继续说明最重要的部分。")
    plan = make_plan(DialogueStage.EXPRESS)
    audit = deterministic_audit(text, TurnAnalysis(), plan)

    assert response_guard_module._content_flags(text)["sensitive_leak"] is True
    assert audit.safety_passed is False
    assert "疑似泄露密钥、系统提示或内部配置" in audit.violations

    final, final_audit, used_fallback, error = guard_response(
        candidate, fallback, TurnAnalysis(), plan,
    )

    assert final == fallback
    assert final_audit.safety_passed is True
    assert used_fallback is True
    assert error is None


def test_offline_pipeline_accepts_software_error_message():
    result = process_message(
        "上传时系统提示是文件格式错误，我有点焦虑。",
        [],
        ConversationState(),
        "我想先说说",
        llm_gateway=None,
    )

    assert result.response.strip()
    assert result.provider_used == "offline"
    assert result.audit.safety_passed is True
    assert result.used_fallback is False
    assert result.error_code is None
