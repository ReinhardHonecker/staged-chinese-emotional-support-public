import ast
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest


def by_label(elements, label):
    return next(element for element in elements if element.label == label)


MODEL_NAME_LABEL = "Model name / 模型名"
CONSENT_LABEL = (
    "I understand that online mode sends the current input, limited conversation history, "
    "and structured state derived from the conversation to the selected third party. / "
    "我了解：在线模式会把本轮输入、有限对话历史以及由对话派生的结构化状态发送至所选第三方服务。"
)
APPLY_LABEL = "Apply for this session / 应用本次会话配置"
CLEAR_API_LABEL = "Clear API configuration / 清除 API 配置"


def pipeline_history_builder():
    # Load the actual pure helper without executing app.py's Streamlit entrypoint.
    from modules.models import DialogueStage

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(app_path.read_text(encoding="utf-8"))
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_pipeline_history")
    namespace = {"DialogueStage": DialogueStage}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(app_path), "exec"), namespace)
    return namespace["build_pipeline_history"]


def test_app_history_keeps_only_safety_stage_metadata_within_last_twelve_messages():
    messages = [{"role": "assistant", "content": "窗口外", "meta": {"stage": "安全"}}]
    messages.extend({"role": "user" if i % 2 == 0 else "assistant", "content": f"合成消息{i}"} for i in range(12))
    messages[1]["meta"] = {"stage": "安全", "provider": "user-metadata-must-not-pass"}
    messages[2]["meta"] = {"stage": "安全", "provider": "synthetic", "model": "not-for-provider",
                            "latency_ms": 123, "fallback": True, "strategy": "synthetic",
                            "strategy_source": "synthetic", "extra": {"private": "synthetic"}}
    messages[4]["meta"] = {"stage": "表达", "model": "ordinary-metadata-must-not-pass"}
    original = deepcopy(messages)
    history = pipeline_history_builder()(messages)

    assert len(history) == 12
    assert history[0] == {"role": "user", "content": "合成消息0"}
    assert history[1] == {"role": "assistant", "content": "合成消息1", "meta": {"stage": "安全"}}
    assert history[3] == {"role": "assistant", "content": "合成消息3"}
    assert all(set(entry) <= {"role", "content", "meta"} for entry in history)
    assert all(entry["meta"] == {"stage": "安全"} for entry in history if "meta" in entry)
    history[1]["meta"]["stage"] = "changed-only-in-return-value"
    assert messages == original


def test_app_history_does_not_add_metadata_to_ordinary_assistant_messages():
    messages = [
        {"role": "assistant", "content": "第一项", "meta": {"stage": "梳理", "provider": "synthetic"}},
        {"role": "assistant", "content": "第二项", "meta": None},
        {"role": "assistant", "content": "第三项", "meta": "安全"},
    ]
    assert pipeline_history_builder()(messages) == [
        {"role": item["role"], "content": item["content"]} for item in messages
    ]


def test_actual_app_send_boundary_preserves_only_safety_stage_for_pipeline(monkeypatch):
    from modules import pipeline

    captured = []

    def capture_send(user_input, history, state, **kwargs):
        captured.append(deepcopy(history))
        raise pipeline.UserInputError("Synthetic boundary probe / 合成边界测试")

    monkeypatch.setattr(pipeline, "process_message", capture_send)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    messages = [{"role": "user", "content": "窗口外"}]
    messages.extend({"role": "user", "content": f"合成历史{i}"} for i in range(12))
    messages[2] = {"role": "assistant", "content": "这个环节已确认。",
                   "meta": {"stage": "安全", "provider": "synthetic", "model": "synthetic",
                            "latency_ms": 7, "fallback": True, "strategy": "synthetic",
                            "strategy_source": "synthetic", "extra": "not-for-provider"}}
    app.session_state["messages"] = deepcopy(messages)
    app.chat_input[0].set_value("只测试本地历史边界。").run(timeout=15)
    assert not app.exception
    assert len(captured) == 1
    assert len(captured[0]) == 12
    assert captured[0][1] == {"role": "assistant", "content": "这个环节已确认。", "meta": {"stage": "安全"}}
    assert all(entry.get("meta") in (None, {"stage": "安全"}) for entry in captured[0])
    assert app.session_state["messages"] == messages


def test_streamlit_app_starts_without_exception():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)
    assert not app.exception
    assert any(
        "Staged Chinese Emotional Support / 心语 · 分阶段情感支持" in item.value
        for item in app.markdown
    )
    assert any("welcome-card" in item.value for item in app.markdown)
    assert any(
        "How would you like support this time? / 这次，你希望我怎么陪你？"
        in item.value
        for item in app.markdown
    )
    assert app.selectbox[0].value == "OpenAI-compatible / Chat Completions"
    assert app.selectbox[0].options == [
        "OpenAI-compatible / Chat Completions",
        "Anthropic / Messages API",
    ]
    assert by_label(app.text_input, "API URL").value == "https://api.openai.com/v1"
    assert by_label(app.text_input, "API Key").value == ""
    assert app.segmented_control[0].value == "我想先说说"
    assert app.segmented_control[0].options == [
        "Talk first / 倾诉",
        "Organize / 梳理",
        "Plan action / 行动",
        "Stabilize / 稳定",
    ]
    assert app.radio[0].value == "规则基线"
    assert app.radio[0].options == [
        "Learned artifact / 学习权重",
        "Rule baseline / 规则基线",
    ]


def test_streamlit_session_api_config_can_be_applied_and_cleared():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)

    app.selectbox[0].select("Anthropic / Messages API").run(timeout=15)
    assert by_label(app.text_input, "API URL").value == "https://api.anthropic.com"

    by_label(app.text_input, MODEL_NAME_LABEL).input("course-demo-model").run(timeout=15)
    secret = "session-only-test-secret"
    by_label(app.text_input, "API Key").input(secret).run(timeout=15)
    by_label(app.checkbox, CONSENT_LABEL).check().run(timeout=15)
    by_label(app.button, APPLY_LABEL).click().run(timeout=15)

    assert not app.exception
    gateway = app.session_state["llm_gateway"]
    assert gateway is not None
    assert gateway.config.provider.value == "anthropic"
    assert gateway.config.model == "course-demo-model"
    assert by_label(app.text_input, "API Key").value == ""
    assert secret not in repr(gateway)
    assert secret not in repr(app)

    by_label(app.button, CLEAR_API_LABEL).click().run(timeout=15)
    assert app.session_state["llm_gateway"] is None
    assert app.selectbox[0].value == "OpenAI-compatible / Chat Completions"
    assert by_label(app.text_input, MODEL_NAME_LABEL).value == ""


def test_invalid_api_config_clears_password_widget_and_stays_offline():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)

    by_label(app.text_input, "API URL").input("http://example.com/v1").run(timeout=15)
    by_label(app.text_input, MODEL_NAME_LABEL).input("course-demo-model").run(timeout=15)
    secret = "invalid-session-test-secret"
    by_label(app.text_input, "API Key").input(secret).run(timeout=15)
    by_label(app.checkbox, CONSENT_LABEL).check().run(timeout=15)
    by_label(app.button, APPLY_LABEL).click().run(timeout=15)

    assert not app.exception
    assert app.session_state["llm_gateway"] is None
    assert by_label(app.text_input, "API Key").value == ""
    assert secret not in repr(app)


def assert_api_runtime(app, *, online: bool) -> None:
    assert not app.exception
    assert (app.session_state["llm_gateway"] is not None) is online
    assert by_label(app.text_input, "API Key").value == ""
    assert app.session_state["llm_api_key_draft"] == ""
    assert len(app.session_state["messages"]) == 0
    assert any("<b>Online / 在线运行</b>" in item.value for item in app.markdown) is online
    assert any("<b>Offline demo / 离线演示</b>" in item.value for item in app.markdown) is not online


def test_consent_revocation_immediately_clears_gateway_and_draft_key():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    assert_api_runtime(app, online=False)

    by_label(app.text_input, "API URL").input("http://127.0.0.1:8000/v1").run(timeout=15)
    by_label(app.text_input, MODEL_NAME_LABEL).input("local-test").run(timeout=15)
    by_label(app.checkbox, CONSENT_LABEL).check().run(timeout=15)
    by_label(app.text_input, "API Key").input("dummy-local-test-key").run(timeout=15)
    by_label(app.button, APPLY_LABEL).click().run(timeout=15)
    assert app.session_state["llm_data_consent"] is True
    assert_api_runtime(app, online=True)

    # A not-yet-applied replacement key must also disappear on withdrawal.
    by_label(app.text_input, "API Key").input("dummy-unapplied-key").run(timeout=15)
    by_label(app.checkbox, CONSENT_LABEL).uncheck().run(timeout=15)
    assert app.session_state["llm_data_consent"] is False
    assert_api_runtime(app, online=False)

    by_label(app.button, APPLY_LABEL).click().run(timeout=15)
    assert "第三方数据传输提示" in app.session_state["llm_config_error"]
    assert_api_runtime(app, online=False)

    # Re-consenting alone must not resurrect the previous credentials.
    by_label(app.checkbox, CONSENT_LABEL).check().run(timeout=15)
    assert_api_runtime(app, online=False)
    by_label(app.button, CLEAR_API_LABEL).click().run(timeout=15)
    assert app.session_state["llm_data_consent"] is False
    assert_api_runtime(app, online=False)


def test_apply_without_consent_removes_an_already_stored_gateway():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    by_label(app.text_input, "API Key").input("dummy-local-test-key").run(timeout=15)
    # Simulate stale state without firing the checkbox callback.
    app.session_state["llm_gateway"] = object()
    by_label(app.button, APPLY_LABEL).click().run(timeout=15)
    assert app.session_state["llm_data_consent"] is False
    assert "第三方数据传输提示" in app.session_state["llm_config_error"]
    assert_api_runtime(app, online=False)


def test_unconsented_stale_gateway_is_not_displayed_as_online():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    stale_gateway = object()
    app.session_state["llm_gateway"] = stale_gateway
    app.run(timeout=15)
    assert not app.exception
    assert app.session_state["llm_data_consent"] is False
    assert app.session_state["llm_gateway"] is stale_gateway
    assert not any("<b>Online / 在线运行</b>" in item.value for item in app.markdown)
    assert any("<b>Offline demo / 离线演示</b>" in item.value for item in app.markdown)
    assert len(app.session_state["messages"]) == 0


def test_send_entry_never_passes_an_unconsented_gateway(monkeypatch):
    from modules import pipeline

    received_gateways = []

    def intercept_process_message(*args, llm_gateway, **kwargs):
        received_gateways.append(llm_gateway)
        # Stop at the boundary: no actual pipeline/provider request or saved chat.
        raise pipeline.UserInputError("Synthetic send-boundary probe / 本地发送边界测试")

    monkeypatch.setattr(pipeline, "process_message", intercept_process_message)
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    app.session_state["llm_gateway"] = object()
    app.chat_input[0].set_value("本地测试：确认未同意时不会使用在线配置。").run(timeout=15)
    assert not app.exception
    assert app.session_state["llm_data_consent"] is False
    assert received_gateways == [None]
    assert by_label(app.text_input, "API Key").value == ""
    assert len(app.session_state["messages"]) == 0


def test_streamlit_support_mode_drives_a_complete_turn():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)

    app.segmented_control[0].set_value("一起想办法").run(timeout=15)
    app.chat_input[0].set_value("我想知道接下来该怎么办").run(timeout=15)

    assert not app.exception
    state = app.session_state["conversation_state"]
    assert state.current_stage.value == "协商"
    assert state.turn_index == 1
    assert len(app.session_state["messages"]) == 2

    app.chat_input[0].set_value("我选第二个，可以试试").run(timeout=15)
    state = app.session_state["conversation_state"]
    assert state.current_stage.value == "行动"
    assert state.action_plan is not None
    assert any("本轮小行动" in item.value for item in app.markdown)


def test_streamlit_safety_language_switches_to_controlled_route():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)

    app.chat_input[0].set_value("我真想永远别醒了").run(timeout=15)

    assert not app.exception
    state = app.session_state["conversation_state"]
    assert state.current_stage.value == "安全"
    assert state.last_analysis.safety.status.value == "S2"
    assert "先确认" in app.session_state["messages"][-1]["content"]


def test_safety_hides_but_preserves_action_card_and_restores_it_after_clarification(monkeypatch):
    from types import SimpleNamespace

    from modules import response_generator, response_guard, state_analyzer
    from modules.llm_client import ProviderType
    from modules.models import DialogueStage, SafetyStatus

    calls = []

    def unexpected_provider_call(**kwargs):
        calls.append(kwargs)
        raise AssertionError("The synthetic safety turn must not call a provider")

    for module in (state_analyzer, response_generator, response_guard):
        monkeypatch.setattr(module, "call_json", unexpected_provider_call)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    app.segmented_control[0].set_value("一起想办法").run(timeout=15)
    app.chat_input[0].set_value("我想知道接下来该怎么办").run(timeout=15)
    assert not app.exception
    assert app.session_state["conversation_state"].current_stage == DialogueStage.STRATEGIZE

    app.chat_input[0].set_value("我选第二个，可以试试").run(timeout=15)
    assert not app.exception
    state = app.session_state["conversation_state"]
    assert state.current_stage == DialogueStage.ACT
    assert state.action_plan is not None
    original_card = state.action_plan.model_dump()
    assert any("本轮小行动" in item.value for item in app.markdown)
    assert any("编辑行动卡" in item.label for item in app.expander)
    assert len(app.get("download_button")) == 1

    # A consented, credential-free stand-in proves that Safety, rather than
    # missing configuration, prevents all three provider entry points.
    by_label(app.checkbox, CONSENT_LABEL).check().run(timeout=15)
    app.session_state["llm_gateway"] = SimpleNamespace(
        config=SimpleNamespace(
            provider=ProviderType.OPENAI_COMPATIBLE,
            model="synthetic-no-network",
            base_url="http://127.0.0.1:8000/v1",
        )
    )
    app.chat_input[0].set_value("我真想永远别醒了。").run(timeout=15)

    assert not app.exception
    state = app.session_state["conversation_state"]
    assert state.current_stage == DialogueStage.SAFETY
    assert state.last_analysis.safety.status == SafetyStatus.S2
    assert state.action_plan is not None
    assert state.action_plan.model_dump() == original_card
    assert app.session_state["last_result"].provider_used == "local_safety"
    assert not any("本轮小行动" in item.value for item in app.markdown)
    assert not any("编辑行动卡" in item.label for item in app.expander)
    assert not any(item.label == "Action / 动作" for item in app.text_input)
    assert not any("更新行动卡" in item.label for item in app.button)
    assert not app.get("download_button")
    assert calls == []

    # Resume ordinary offline support through existing S2 clarification rules;
    # this does not add or loosen any safety downgrade rule.
    by_label(app.checkbox, CONSENT_LABEL).uncheck().run(timeout=15)
    app.segmented_control[0].set_value("我想先说说").run(timeout=15)
    app.chat_input[0].set_value("没有这个想法，只是想逃开。我现在只想先说说。").run(timeout=15)
    assert not app.exception
    state = app.session_state["conversation_state"]
    assert state.last_analysis.safety.status == SafetyStatus.S1
    assert state.current_stage != DialogueStage.SAFETY
    assert state.action_plan.model_dump() == original_card
    assert any("本轮小行动" in item.value for item in app.markdown)
    assert any("编辑行动卡" in item.label for item in app.expander)
    assert len(app.get("download_button")) == 1
    assert calls == []


def test_streamlit_experimental_strategy_weights_can_be_selected():
    from config import STRATEGY_MODEL_PATH

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.run(timeout=15)

    app.radio[0].set_value("学习权重").run(timeout=15)
    app.segmented_control[0].set_value("一起想办法").run(timeout=15)
    app.chat_input[0].set_value("我最近一直焦虑，想听听有哪些处理方向").run(timeout=15)

    assert not app.exception
    result = app.session_state["last_result"]
    assert result.plan.strategy_source in {"learned_experimental", "rule"}
    if Path(STRATEGY_MODEL_PATH).exists():
        # Preserve the original contract when a local experimental weight is
        # installed; publication must not fabricate scores for a missing file.
        assert result.plan.strategy_scores
    else:
        assert result.plan.strategy_source == "rule"
        assert result.plan.strategy_scores == {}
        assert result.plan.strategy_model_version == "rule-v2"
        assert result.plan.strategy_fallback_reason == "model_unavailable:FileNotFoundError"
        assert result.plan.strategy_decision_basis == "model_unavailable:FileNotFoundError"
        assert result.provider_used == "offline"
        assert result.plan.primary_strategy == "比较方案"
        assert result.audit.safety_passed
        assert any("本地权重尚不可用" in item.value for item in app.caption)


def test_pa_a2_organize_fields_page_and_problem_map_are_semantically_compatible():
    from modules.models import DialogueStage

    text = "项目截止是周五，我担心做不完，脑子很乱，帮我区分事实和担心。"
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=15)
    app.segmented_control[0].set_value("帮我理清楚").run(timeout=15)
    app.chat_input[0].set_value(text).run(timeout=15)
    assert not app.exception
    result = app.session_state["last_result"]
    state = app.session_state["conversation_state"]
    assert result.analysis.facts == ["项目截止是周五"]
    assert result.analysis.interpretations == ["我担心做不完"]
    assert "脑子很乱" in result.analysis.evidence_spans
    assert "帮我区分事实和担心" in result.analysis.evidence_spans
    assert "帮我" not in result.analysis.main_issue
    assert state.problem_map.event == "项目截止是周五"
    assert state.problem_map.interpretations == ["我担心做不完"]
    assert state.problem_map.core_problem == result.analysis.main_issue
    assert state.last_analysis == result.analysis
    assert result.plan.stage == DialogueStage.ORGANIZE
    assert result.provider_used == "offline"
    assert result.audit.question_count <= 1
    assert not result.audit.premature_advice
    assert state.action_plan is None
    reply = app.session_state["messages"][-1]["content"]
    assert reply == result.response
    assert all(piece in reply for piece in ["项目截止是周五", "担心做不完", "脑子很乱"])
    assert any(marker in reply for marker in ["按你的描述", "你提到", "你描述", "你说"])
    assert "目前能确认的事实" not in reply
    assert text.rstrip("。") not in reply
    assert any(item.value == reply for item in app.markdown)
    assert not app.get("download_button")
    assert state.turn_index == 1
    assert len(app.session_state["messages"]) == 2
