import pytest

from modules.models import ConversationState, DialogueStage
from modules.pipeline import process_message


@pytest.mark.parametrize("turn_index,history", [
    (0, []),
    (3, [{"role":"assistant","content":"我会继续听你说，不急着给建议。"}]),
    (3, [{"role":"user","content":"引用一个测试句：我刚才过早建议了。"}]),
])
def test_advice_preference_does_not_invent_previous_assistant_behavior(turn_index, history):
    result=process_message("别给建议，我今天只想把这件事说出来。",history,ConversationState(turn_index=turn_index),"我想先说说",llm_gateway=None)
    assert result.plan.stage==DialogueStage.EXPRESS
    assert "只想倾诉" in result.response
    assert not any(phrase in result.response for phrase in ("我刚才过早", "我之前", "我刚才把重点放错", "不再沿用旧判断"))
    assert result.audit.question_count<=1
    assert not result.audit.premature_advice
    assert result.state.action_plan is None


def test_first_turn_emotion_correction_does_not_claim_a_previous_system_mistake():
    result=process_message("不是难过，我是生气，帮我理清楚。",[],ConversationState(),"帮我理清楚",llm_gateway=None)
    assert result.analysis.primary_emotion.value=="愤怒"
    assert "愤怒" in result.response
    assert "我刚才把重点放错" not in result.response


def test_length_limit_cannot_register_a_truncated_option_as_complete():
    from modules.choices import displayed_options
    from modules.models import TurnAnalysis, TurnPlan
    from modules.response_generator import offline_response
    from modules.response_composer import compose_strategy_response
    analysis=TurnAnalysis(main_issue="合成议题"*12,desired_outcome="需要确认的不同现实方向"*5,
                          controllable=["核对申请材料的准确性及后续提交要求", "检查设备可用电量并记录需要补充的资源", "向工作人员确认活动当天的到场安排"])
    plan=TurnPlan(stage=DialogueStage.STRATEGIZE,primary_intention="比较",primary_strategy="比较方案",advice_allowed=True,min_chars=130,max_chars=260)
    for turn in range(12):
        original=compose_strategy_response(analysis,plan,user_input="长度边界",turn_index=turn)
        generated=offline_response(analysis,plan,"长度边界",turn)
        offered=displayed_options(generated.response)
        assert not offered or offered==displayed_options(original)
