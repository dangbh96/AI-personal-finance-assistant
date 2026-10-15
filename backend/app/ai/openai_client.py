"""Điểm truy cập duy nhất tới OpenAI (ADR-003).

- Model đọc từ env (`OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`, `OPENAI_EMBEDDING_MODEL`).
- Timeout + retry có backoff cho lỗi mạng / 429 / 5xx (tối đa 2 lần, do OpenAI SDK thực hiện).
- Structured output: JSON schema strict sinh từ Pydantic, validate lại bằng Pydantic; nếu output
  không hợp lệ thì gửi lỗi cho model và thử lại 1 lần, sau đó raise `AIUnavailable`.
- Log tác vụ, model, token, latency — không log API key / nội dung prompt.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import openai
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_NETWORK_RETRIES = 2
MAX_OUTPUT_RETRIES = 1
_UNSUPPORTED_KEYWORDS = frozenset({"minLength", "maxLength", "default"})

Message = dict[str, str]


class AIUnavailable(DomainError):
    """AI không dùng được (chưa cấu hình, lỗi mạng, output sai); phần deterministic vẫn chạy."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message, code)
        self.status_code = status_code


class OutputValidationError(ValueError):
    """Output đúng schema nhưng sai nghiệp vụ (vd category ngoài danh sách) → cho model sửa."""


@dataclass(frozen=True)
class ChatResult:
    content: str | None
    refusal: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.openai_api_key and settings.openai_api_key.strip())


def model_fast(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_model_fast


def model_smart(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_model_smart


def embedding_model(settings: Settings | None = None) -> str:
    return (settings or get_settings()).openai_embedding_model


def ensure_configured() -> None:
    if not is_configured():
        raise AIUnavailable(
            "AI_NOT_CONFIGURED",
            "Chưa cấu hình AI (thiếu OPENAI_API_KEY). Bạn vẫn có thể nhập giao dịch thủ công.",
        )


@lru_cache(maxsize=4)
def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, max_retries=MAX_NETWORK_RETRIES)


def _chat_json(
    *, model: str, messages: list[Message], schema_name: str, schema: dict[str, Any], timeout: float
) -> ChatResult:
    """Một lời gọi Chat Completions với `response_format=json_schema` (strict)."""
    api_key = get_settings().openai_api_key or ""
    response = _client(api_key.strip()).chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
        temperature=0,
        timeout=timeout,
    )
    choice = response.choices[0]
    usage = response.usage
    return ChatResult(
        content=choice.message.content,
        refusal=getattr(choice.message, "refusal", None),
        finish_reason=choice.finish_reason,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
    )


def _map_openai_error(exc: openai.OpenAIError) -> AIUnavailable:
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return AIUnavailable("AI_AUTH_FAILED", "OPENAI_API_KEY không hợp lệ hoặc không có quyền.")
    if isinstance(exc, openai.RateLimitError):
        return AIUnavailable(
            "AI_RATE_LIMITED", "AI đang quá tải hoặc hết hạn mức. Bạn thử lại sau ít phút nhé."
        )
    if isinstance(exc, openai.APITimeoutError):
        return AIUnavailable("AI_TIMEOUT", "AI phản hồi quá lâu. Bạn thử lại sau nhé.")
    return AIUnavailable("AI_UNAVAILABLE", "Không kết nối được dịch vụ AI. Bạn thử lại sau nhé.")


def _validation_feedback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}" for e in error.errors()
        )
    else:
        details = str(error)
    return (
        "Output vừa rồi không hợp lệ: "
        f"{details}. Hãy sửa và trả lại toàn bộ JSON đúng schema và đúng các quy tắc."
    )


def _strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON schema strict cho OpenAI, bỏ keyword strict mode không hỗ trợ (Pydantic vẫn check)."""

    def clean(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYWORDS}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(to_strict_json_schema(schema))


def structured_completion[T: BaseModel](
    schema: type[T],
    messages: list[Message],
    *,
    task: str,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    validate: Callable[[T], None] | None = None,
) -> tuple[T, str]:
    """Gọi model và trả `(output đã validate, tên model)`.

    `validate` kiểm tra nghiệp vụ, raise `OutputValidationError` để model được sửa 1 lần.
    """
    ensure_configured()
    model = model or model_fast()
    json_schema = _strict_schema(schema)
    conversation = list(messages)

    for attempt in range(MAX_OUTPUT_RETRIES + 1):
        started = time.perf_counter()
        try:
            result = _chat_json(
                model=model,
                messages=conversation,
                schema_name=schema.__name__,
                schema=json_schema,
                timeout=timeout,
            )
        except openai.OpenAIError as exc:
            logger.warning("ai task=%s model=%s error=%s", task, model, type(exc).__name__)
            raise _map_openai_error(exc) from exc
        logger.info(
            "ai task=%s model=%s attempt=%d prompt_tokens=%s completion_tokens=%s latency_ms=%d",
            task,
            model,
            attempt + 1,
            result.prompt_tokens,
            result.completion_tokens,
            (time.perf_counter() - started) * 1000,
        )

        if result.refusal or not result.content:
            raise AIUnavailable(
                "AI_INVALID_OUTPUT", "AI không xử lý được yêu cầu này.", status_code=502
            )
        try:
            output = schema.model_validate_json(result.content)
            if validate:
                validate(output)
            return output, model
        except (ValidationError, OutputValidationError) as exc:
            logger.warning(
                "ai task=%s model=%s attempt=%d invalid_output=%s",
                task,
                model,
                attempt + 1,
                _validation_feedback(exc),
            )
            conversation += [
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": _validation_feedback(exc)},
            ]

    raise AIUnavailable(
        "AI_INVALID_OUTPUT",
        "AI trả kết quả không hợp lệ. Bạn thử diễn đạt lại hoặc nhập thủ công nhé.",
        status_code=502,
    )
