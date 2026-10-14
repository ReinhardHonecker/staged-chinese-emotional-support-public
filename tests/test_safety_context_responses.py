import pytest

from modules import response_generator, response_guard, state_analyzer
from modules.models import (
    ConversationState,
    DialogueStage,
    SafetySignal,
    SafetyStatus,
    TurnAnalysis,
)
from modules.pipeline import process_message
from modules.response_generator import build_safety_response
from modules.response_planner import _safety_plan


@pytest.fixture
def external_calls(monkeypatch):
    calls = []

    def unexpected_call(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Safety context responses must stay local")

    monkeypatch.setattr(state_analyzer, "call_json", unexpected_call)
    monkeypatch.setattr(response_generator, "call_json", unexpected_call)
    monkeypatch.setattr(response_guard, "call_json", unexpected_call)
    return calls


def _assert_contextual_s4(result):
    assert result.analysis.safety.status == SafetyStatus.S4
    assert result.plan.stage == DialogueStage.SAFETY
    assert result.provider_used == "local_safety"
    assert result.model_used == "固定安全协议"
    assert result.used_fallback is False
    assert result.error_code is None
    assert "110" in result.response
    assert "120" in result.response
    assert "到场" in result.response
    assert "伤害你的东西" not in result.response
    assert "打开门" not in result.response
    assert "伤害自己" not in result.response
    assert "具体计划" not in result.response
    assert "具体方法" not in result.response
    assert result.audit.question_count == 0
    assert result.audit.safety_passed
    assert result.audit.length_passed


@pytest.mark.parametrize(
    "user_input",
    [
        "室友告诉我他不想活，已经有具体计划。",
        "室友告诉我他不想活，已经有具体计划。我气得想让他去死。",
    ],
)
def test_single_turn_third_party_s4_keeps_subject_and_stays_local(
    external_calls, user_input
):
    result = process_message(
        user_input,
        [],
        ConversationState(),
        "我想先说说",
        llm_gateway=object(),
    )

    _assert_contextual_s4(result)
    assert result.analysis.safety.subject == "第三方"
    assert result.analysis.safety.harm_target == "第三方自伤"
    assert "风险主体是你提到的那个人，不是你本人" in result.response
    assert "对方所在地的 110/120" in result.response
    assert "对方的位置" in result.response
    assert "当地能实际到场" in result.response
    assert "仅在自身安全前提下保持电话或消息连接" in result.response
    assert "不要独自前往或独自处置" in result.response
    assert "接手陪伴" in result.response
    assert result.plan.primary_strategy == "第三方紧急安全连接"
    assert "第三方" in result.plan.primary_intention
    assert "明确风险主体不是当前用户" in result.plan.response_outline
    assert external_calls == []


def test_other_harm_s2_to_s4_keeps_distance_and_stays_local(external_calls):
    first_text = "我气得想让他去死。"
    gateway = object()
    first = process_message(
        first_text,
        [],
        ConversationState(),
        "我想先说说",
        llm_gateway=gateway,
    )

    assert first.analysis.safety.status == SafetyStatus.S2
    assert first.analysis.safety.harm_target == "他伤"
    assert first.provider_used == "local_safety"
    assert "不联系或靠近对方" in first.response
    assert external_calls == []

    result = process_message(
        "我现在控制不住自己。",
        [
            {"role": "user", "content": first_text},
            {"role": "assistant", "content": first.response},
        ],
        first.state,
        "我想先说说",
        llm_gateway=gateway,
    )

    _assert_contextual_s4(result)
    assert result.analysis.safety.subject == "本人"
    assert result.analysis.safety.harm_target == "他伤"
    assert "停止接触对方" in result.response
    assert "保持现实距离" in result.response
    assert "不要前往对方所在地" in result.response
    assert "联系 110，明确告知存在他伤风险" in result.response
    assert "若已有伤者，再联系 120" in result.response
    assert "能实际到场的可信任者或现场工作人员" in result.response
    assert "联系现实支持" in result.response
    assert result.plan.primary_strategy == "他伤紧急安全分流"
    assert "停止接触、保持距离" in result.plan.primary_intention
    assert "不走自伤模板" in result.plan.response_outline
    assert external_calls == []


@pytest.mark.parametrize("status", [SafetyStatus.S2, SafetyStatus.S3, SafetyStatus.S4])
def test_third_party_context_has_priority_over_other_harm(status):
    analysis = TurnAnalysis(
        safety=SafetySignal(status=status, subject="第三方", harm_target="他伤")
    )

    response = build_safety_response(analysis)
    intention, primary, _, outline = _safety_plan(analysis)

    assert "对他人的强烈愤怒" not in response
    assert "停止接触对方" not in response
    assert "第三方" in intention
    assert "明确风险主体不是当前用户" in outline
    if status == SafetyStatus.S4:
        assert "风险主体是你提到的那个人，不是你本人" in response
        assert primary == "第三方紧急安全连接"
    else:
        assert primary == "第三方安全连接"


def test_self_harm_s4_retains_existing_protocol_and_stays_local(external_calls):
    result = process_message(
        "我现在不能保证自己安全。",
        [],
        ConversationState(),
        "先帮我稳一下",
        llm_gateway=object(),
    )

    assert result.analysis.safety.status == SafetyStatus.S4
    assert result.analysis.safety.subject == "本人"
    assert result.analysis.safety.harm_target == "自伤"
    assert result.provider_used == "local_safety"
    assert result.plan.primary_strategy == "紧急安全分流"
    assert "伤害你的东西" in result.response
    assert "拨打 120" in result.response
    assert "拨打 110" in result.response
    assert "12356" in result.response
    assert result.audit.safety_passed
    assert result.audit.question_count == 0
    assert external_calls == []
