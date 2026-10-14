from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("index", [1, 3])
def test_real_app_choice_uses_the_shown_option_and_rerun_does_not_expire_it(index):
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py")).run(timeout=15)
    app.segmented_control[0].set_value("一起想办法").run(timeout=15)
    app.chat_input[0].set_value("我可以先核对报名条件。我可以先检查设备电量。我可以先整理可用时间。先比较方向，暂时不决定。").run(timeout=15)
    state=app.session_state["conversation_state"]
    options=list(state.pending_options)
    assert len(options)==3
    assert state.options_turn==state.turn_index==1
    assert all(option in app.session_state["messages"][-1]["content"] for option in options)
    app.run(timeout=15)
    assert app.session_state["conversation_state"].pending_options==options
    assert len(app.session_state["messages"])==2
    app.chat_input[0].set_value(f"我选第{index}个，可以试试。").run(timeout=15)
    assert not app.exception
    result=app.session_state["last_result"]
    assert result.plan.selected_option==options[index-1]
    assert result.state.action_plan.action in result.response
    assert options[index-1].removeprefix("我可以先") in result.state.action_plan.action
    assert not result.state.pending_options
    assert len(app.session_state["messages"])==4


def test_real_app_orphan_choice_shows_clarification_without_card():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py")).run(timeout=15)
    app.segmented_control[0].set_value("一起想办法").run(timeout=15)
    app.chat_input[0].set_value("我选第二个，可以试试。").run(timeout=15)
    assert not app.exception
    result=app.session_state["last_result"]
    assert result.plan.choice_clarification
    assert result.state.action_plan is None
    assert not any("本轮小行动" in item.value for item in app.markdown)
    assert not app.get("download_button")
