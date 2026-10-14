import sqlite3
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from modules.llm_client import (
    JSON_ONLY_INSTRUCTION,
    LLMGateway,
    LLMRuntimeConfig,
    LLMServiceError,
    ProviderType,
    call_json,
)
from modules import metrics
from modules.models import ConversationState
from modules.pipeline import process_message


TEST_SECRET = "session-only-test-secret"


def make_config(
    provider: ProviderType = ProviderType.OPENAI_COMPATIBLE,
    base_url: str | None = None,
) -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        provider=provider,
        base_url=base_url
        or (
            "https://api.openai.com/v1"
            if provider == ProviderType.OPENAI_COMPATIBLE
            else "https://api.anthropic.com"
        ),
        api_key=TEST_SECRET,
        model="course-demo-model",
        max_retries=0,
    )


def gateway_with_client(config: LLMRuntimeConfig, client: object) -> LLMGateway:
    gateway = object.__new__(LLMGateway)
    gateway.config = config
    gateway._client = client
    return gateway


class RecordingCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def openai_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_runtime_config_rejects_unsafe_urls_and_empty_fields():
    for invalid_url in (
        "http://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?token=value",
        "https://example.com/v1#fragment",
        "ftp://example.com/v1",
    ):
        with pytest.raises(ValidationError):
            make_config(base_url=invalid_url)

    assert make_config(base_url="http://localhost:8000/v1").base_url.endswith("/v1")
    assert make_config(base_url="http://127.0.0.1:8000/v1").base_url.endswith("/v1")
    assert make_config(base_url="http://[::1]:8000/v1").base_url.endswith("/v1")

    with pytest.raises(ValidationError):
        LLMRuntimeConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            base_url="https://api.openai.com/v1",
            api_key=" ",
            model="course-demo-model",
        )
    with pytest.raises(ValidationError):
        LLMRuntimeConfig(
            provider=ProviderType.OPENAI_COMPATIBLE,
            base_url="https://api.openai.com/v1",
            api_key=TEST_SECRET,
            model=" ",
        )


def test_secret_is_excluded_from_serialization_and_representations():
    config = make_config()
    gateway = gateway_with_client(config, object())

    assert "api_key" not in config.model_dump()
    assert TEST_SECRET not in config.model_dump_json()
    assert TEST_SECRET not in repr(config)
    assert TEST_SECRET not in repr(gateway)


def test_openai_chat_completions_json_mapping_and_single_compatibility_retry():
    class UnsupportedResponseFormat(Exception):
        status_code = 400

    completions = RecordingCompletions(
        [
            UnsupportedResponseFormat("response_format json_object is unsupported"),
            openai_response('{"accepted": true}'),
        ]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    gateway = gateway_with_client(make_config(), client)

    result = call_json(
        gateway=gateway,
        messages=[{"role": "user", "content": "返回结构化结果"}],
        temperature=0.1,
        max_tokens=128,
    )

    assert result == {"accepted": True}
    assert len(completions.calls) == 2
    assert completions.calls[0]["model"] == "course-demo-model"
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in completions.calls[1]
    assert completions.calls[0]["messages"][0]["content"] == JSON_ONLY_INSTRUCTION


def test_anthropic_messages_mapping_promotes_system_and_merges_text_blocks():
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="text", text='{"accepted":'),
                    SimpleNamespace(type="text", text="true}"),
                ]
            )

    gateway = gateway_with_client(
        make_config(ProviderType.ANTHROPIC),
        SimpleNamespace(messages=Messages()),
    )
    result = call_json(
        gateway=gateway,
        messages=[
            {"role": "system", "content": "遵循课程实验约束。"},
            {"role": "user", "content": "第一段"},
            {"role": "user", "content": "第二段"},
        ],
        temperature=0.0,
        max_tokens=128,
    )

    assert result == {"accepted": True}
    assert len(calls) == 1
    assert JSON_ONLY_INSTRUCTION in calls[0]["system"]
    assert "遵循课程实验约束。" in calls[0]["system"]
    assert calls[0]["messages"] == [
        {"role": "user", "content": "第一段\n\n第二段"}
    ]


@pytest.mark.parametrize(
    ("status_code", "exception_name", "expected_code"),
    [
        (401, "ProviderError", "authentication_failed"),
        (429, "ProviderError", "rate_limited"),
        (None, "RequestTimeout", "timeout"),
        (None, "APIConnectionError", "connection_failed"),
    ],
)
def test_provider_errors_are_mapped_without_leaking_raw_details(
    status_code, exception_name, expected_code
):
    error_type = type(exception_name, (Exception,), {"status_code": status_code})
    completions = RecordingCompletions([error_type(f"private detail: {TEST_SECRET}")])
    gateway = gateway_with_client(
        make_config(),
        SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    with pytest.raises(LLMServiceError) as caught:
        gateway.call_llm(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.0,
            max_tokens=32,
        )

    assert caught.value.code == expected_code
    assert TEST_SECRET not in str(caught.value)
    assert TEST_SECRET not in repr(caught.value)
    assert TEST_SECRET not in caught.value.internal_message


def test_empty_content_and_invalid_json_have_stable_error_codes():
    empty = RecordingCompletions([openai_response("")])
    gateway = gateway_with_client(
        make_config(), SimpleNamespace(chat=SimpleNamespace(completions=empty))
    )
    with pytest.raises(LLMServiceError, match="empty_content"):
        gateway.call_llm(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.0,
            max_tokens=32,
        )

    invalid = RecordingCompletions([openai_response("not-json")])
    gateway = gateway_with_client(
        make_config(), SimpleNamespace(chat=SimpleNamespace(completions=invalid))
    )
    with pytest.raises(LLMServiceError, match="invalid_json"):
        call_json(
            gateway=gateway,
            messages=[{"role": "user", "content": "test"}],
            temperature=0.0,
            max_tokens=32,
        )


def test_secret_never_enters_pipeline_result_metrics_or_state_export(tmp_path, monkeypatch):
    gateway = gateway_with_client(make_config(), object())
    result = process_message(
        "我现在不能保证自己安全。",
        [],
        ConversationState(),
        "先帮我稳一下",
        llm_gateway=gateway,
    )
    assert TEST_SECRET not in result.model_dump_json()
    assert TEST_SECRET not in result.state.model_dump_json()

    database = tmp_path / "metrics.sqlite3"
    monkeypatch.setattr(metrics, "METRICS_ENABLED", True)
    monkeypatch.setattr(metrics, "METRICS_DB_PATH", database)
    metrics.record_pipeline_metric(result)

    with sqlite3.connect(database) as connection:
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        rows = connection.execute("SELECT * FROM pipeline_metrics").fetchall()
    assert TEST_SECRET not in repr(schema)
    assert TEST_SECRET not in repr(rows)
