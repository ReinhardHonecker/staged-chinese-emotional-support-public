from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


JSON_ONLY_INSTRUCTION = "只输出一个有效 JSON 值，不要使用 Markdown 代码围栏或额外说明。"
LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ProviderType(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"

    @property
    def display_name(self) -> str:
        return {
            self.OPENAI_COMPATIBLE: "OpenAI-compatible / Chat Completions",
            self.ANTHROPIC: "Anthropic / Messages API",
        }[self]


class LLMRuntimeConfig(BaseModel):
    """Validated, session-only provider configuration.

    The API key is excluded from serialization and representation so it cannot
    accidentally enter metrics, downloads, logs, or debug output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: ProviderType
    base_url: str
    api_key: SecretStr = Field(repr=False, exclude=True)
    model: str = Field(min_length=1, max_length=200)
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    max_retries: int = Field(default=1, ge=0, le=5)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("invalid_api_url")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("api_url_must_not_embed_credentials_or_parameters")
        if parsed.scheme == "http" and parsed.hostname.lower() not in LOCAL_HTTP_HOSTS:
            raise ValueError("http_is_only_allowed_for_localhost")
        return normalized

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("api_key_required")
        return value

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model_required")
        return normalized


class LLMServiceError(RuntimeError):
    def __init__(self, code: str, internal_message: str = ""):
        super().__init__(code)
        self.code = code
        self.internal_message = internal_message


def _error_status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _error_code(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    status = _error_status(exc)
    if status in {401, 403} or "authentication" in name:
        return "authentication_failed"
    if status == 429 or "ratelimit" in name or "rate_limit" in name:
        return "rate_limited"
    if status == 404 and "model" in message:
        return "model_not_found"
    if "timeout" in name or "timed out" in message:
        return "timeout"
    if "connection" in name:
        return "connection_failed"
    if status in {400, 404, 422}:
        return "invalid_request"
    return "service_error"


def _response_format_unsupported(exc: Exception) -> bool:
    if _error_status(exc) not in {400, 404, 422}:
        return False
    message = str(exc).lower()
    return "response_format" in message or "json_object" in message


def _with_json_instruction(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": JSON_ONLY_INSTRUCTION},
        *[{"role": item["role"], "content": item["content"]} for item in messages],
    ]


def _extract_openai_content(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if text:
                parts.append(str(text))
        return "".join(parts).strip()
    return ""


def _anthropic_payload(
    messages: list[dict[str, str]], *, json_mode: bool
) -> tuple[str, list[dict[str, str]]]:
    system_parts = [
        item["content"] for item in messages if item.get("role") in {"system", "developer"}
    ]
    if json_mode:
        system_parts.insert(0, JSON_ONLY_INSTRUCTION)

    conversation: list[dict[str, str]] = []
    for item in messages:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content", ""))
        if conversation and conversation[-1]["role"] == role:
            conversation[-1]["content"] += "\n\n" + content
        else:
            conversation.append({"role": role, "content": content})
    if not conversation:
        conversation.append({"role": "user", "content": "请按照系统指令完成任务。"})
    return "\n\n".join(system_parts), conversation


def _extract_anthropic_content(response: Any) -> str:
    parts = []
    for block in getattr(response, "content", []) or []:
        block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if block_type == "text" and text:
            parts.append(str(text))
    return "".join(parts).strip()


def parse_json_value(raw: str) -> Any:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((index for index in (text.find("{"), text.find("[")) if index >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class LLMGateway:
    """One provider client bound to one Streamlit session."""

    def __init__(self, config: LLMRuntimeConfig):
        self.config = config
        secret = config.api_key.get_secret_value()
        if config.provider == ProviderType.OPENAI_COMPATIBLE:
            self._client = OpenAI(
                api_key=secret,
                base_url=config.base_url,
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )
        else:
            self._client = Anthropic(
                api_key=secret,
                base_url=config.base_url,
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
            )

    def __repr__(self) -> str:
        return (
            "LLMGateway("
            f"provider={self.config.provider.value!r}, "
            f"base_url={self.config.base_url!r}, model={self.config.model!r})"
        )

    def call_llm(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        try:
            if self.config.provider == ProviderType.OPENAI_COMPATIBLE:
                request_messages = _with_json_instruction(messages) if json_mode else messages
                kwargs: dict[str, Any] = {
                    "model": self.config.model,
                    "messages": request_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    response = self._client.chat.completions.create(**kwargs)
                except Exception as exc:
                    if not (json_mode and _response_format_unsupported(exc)):
                        raise
                    kwargs.pop("response_format", None)
                    response = self._client.chat.completions.create(**kwargs)
                content = _extract_openai_content(response)
            else:
                system, conversation = _anthropic_payload(messages, json_mode=json_mode)
                kwargs = {
                    "model": self.config.model,
                    "messages": conversation,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if system:
                    kwargs["system"] = system
                response = self._client.messages.create(**kwargs)
                content = _extract_anthropic_content(response)
            if not content:
                raise LLMServiceError("empty_content")
            return content
        except LLMServiceError:
            raise
        except Exception as exc:
            raise LLMServiceError(_error_code(exc), type(exc).__name__) from exc


def is_llm_configured(gateway: LLMGateway | None) -> bool:
    return gateway is not None


def call_llm(
    *,
    gateway: LLMGateway | None,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> str:
    if gateway is None:
        raise LLMServiceError("missing_api_key")
    return gateway.call_llm(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )


def call_json(**kwargs: Any) -> dict[str, Any]:
    raw = call_llm(json_mode=True, **kwargs)
    try:
        parsed = parse_json_value(raw)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("invalid_json", "JSONDecodeError") from exc
    if not isinstance(parsed, dict):
        raise LLMServiceError("invalid_json", "ExpectedJSONObject")
    return parsed
