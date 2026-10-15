"""Test `openai_client` không gọi mạng: thay `_chat_json` bằng hàng đợi response giả."""

import json

import httpx
import openai
import pytest
from pydantic import BaseModel, field_validator

from app.ai import openai_client
from app.ai.openai_client import AIUnavailable, ChatResult, OutputValidationError
from app.core.config import Settings


class Echo(BaseModel):
    value: int

    @field_validator("value")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("value phải dương")
        return v


def _result(content: str | None, refusal: str | None = None) -> ChatResult:
    return ChatResult(
        content=content,
        refusal=refusal,
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
    )


@pytest.fixture
def fake_chat(monkeypatch):
    """Trả lần lượt các phần tử trong `responses` (ChatResult hoặc Exception); ghi lại các call."""
    calls: list[dict] = []
    responses: list = []

    def _fake(**kwargs):
        calls.append(kwargs)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_chat_json", _fake)
    return calls, responses


MESSAGES = [{"role": "user", "content": "hi"}]


def test_is_configured_reads_api_key():
    assert not openai_client.is_configured(Settings(openai_api_key=None))
    assert not openai_client.is_configured(Settings(openai_api_key="   "))
    assert openai_client.is_configured(Settings(openai_api_key="sk-test"))


def test_not_configured_raises_503(monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)

    with pytest.raises(AIUnavailable) as exc_info:
        openai_client.structured_completion(Echo, MESSAGES, task="test")

    assert exc_info.value.code == "AI_NOT_CONFIGURED"
    assert exc_info.value.status_code == 503


def test_valid_output_returned_with_model(fake_chat):
    calls, responses = fake_chat
    responses.append(_result('{"value": 3}'))

    output, model = openai_client.structured_completion(
        Echo, MESSAGES, task="test", model="gpt-test"
    )

    assert output == Echo(value=3)
    assert model == "gpt-test"
    assert len(calls) == 1
    schema = calls[0]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["value"]
    assert calls[0]["schema_name"] == "Echo"


def test_invalid_output_retried_once_with_error_feedback(fake_chat):
    calls, responses = fake_chat
    responses += [_result('{"value": -1}'), _result('{"value": 2}')]

    output, _ = openai_client.structured_completion(Echo, MESSAGES, task="test", model="m")

    assert output.value == 2
    assert len(calls) == 2
    retry_messages = calls[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": '{"value": -1}'}
    assert "value phải dương" in retry_messages[-1]["content"]


def test_invalid_output_twice_raises_ai_invalid_output(fake_chat):
    calls, responses = fake_chat
    responses += [_result("not json"), _result('{"value": 0}')]

    with pytest.raises(AIUnavailable) as exc_info:
        openai_client.structured_completion(Echo, MESSAGES, task="test", model="m")

    assert exc_info.value.code == "AI_INVALID_OUTPUT"
    assert exc_info.value.status_code == 502
    assert len(calls) == 2


def test_business_validator_triggers_retry(fake_chat):
    calls, responses = fake_chat
    responses += [_result('{"value": 7}'), _result('{"value": 8}')]

    def even_only(output: Echo) -> None:
        if output.value % 2:
            raise OutputValidationError("value phải chẵn")

    output, _ = openai_client.structured_completion(
        Echo, MESSAGES, task="test", model="m", validate=even_only
    )

    assert output.value == 8
    assert "value phải chẵn" in calls[1]["messages"][-1]["content"]


def test_refusal_raises_invalid_output(fake_chat):
    _, responses = fake_chat
    responses.append(_result(None, refusal="I can't help"))

    with pytest.raises(AIUnavailable) as exc_info:
        openai_client.structured_completion(Echo, MESSAGES, task="test", model="m")

    assert exc_info.value.code == "AI_INVALID_OUTPUT"


def _status_error(cls: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": "x"}})
    return cls("x", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (_status_error(openai.AuthenticationError, 401), "AI_AUTH_FAILED"),
        (_status_error(openai.RateLimitError, 429), "AI_RATE_LIMITED"),
        (_status_error(openai.InternalServerError, 500), "AI_UNAVAILABLE"),
        (
            openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com")),
            "AI_TIMEOUT",
        ),
        (
            openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com")),
            "AI_UNAVAILABLE",
        ),
    ],
)
def test_openai_errors_mapped_to_503(fake_chat, error, code):
    _, responses = fake_chat
    responses.append(error)

    with pytest.raises(AIUnavailable) as exc_info:
        openai_client.structured_completion(Echo, MESSAGES, task="test", model="m")

    assert exc_info.value.code == code
    assert exc_info.value.status_code == 503
    assert "sk-" not in exc_info.value.detail


def test_strict_schema_drops_unsupported_keywords():
    class WithLimits(BaseModel):
        name: str = ""
        tags: list[str] = []

    schema = openai_client._strict_schema(WithLimits)

    assert "default" not in json.dumps(schema)
    assert schema["required"] == ["name", "tags"]


def test_client_uses_network_retries():
    client = openai_client._client("sk-test")
    assert client.max_retries == openai_client.MAX_NETWORK_RETRIES
