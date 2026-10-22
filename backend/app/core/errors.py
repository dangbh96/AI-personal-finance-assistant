"""Lỗi nghiệp vụ và handler trả về dạng `{"detail": ..., "code": ...}`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
}


class DomainError(Exception):
    status_code = 422
    # Trường bổ sung trong body lỗi (vd `import_batch_id` của lô đã import — Phase 14).
    extra: dict[str, Any] | None = None

    def __init__(self, detail: str, code: str = "invalid") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class NotFoundError(DomainError):
    status_code = 404

    def __init__(self, detail: str, code: str = "not_found") -> None:
        super().__init__(detail, code)


class ConflictError(DomainError):
    status_code = 409

    def __init__(self, detail: str, code: str = "conflict") -> None:
        super().__init__(detail, code)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={**jsonable_encoder(exc.extra or {}), "detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 404 route không tồn tại, 405 sai method… cũng theo format {"detail", "code"}.
        detail = exc.detail if isinstance(exc.detail, str) else jsonable_encoder(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail, "code": HTTP_ERROR_CODES.get(exc.status_code, "http_error")},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
        )

    @app.middleware("http")
    async def _unhandled_error(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Lỗi không lường trước → 500 `{"detail", "code": "internal_error"}` (log traceback, không
        lộ chi tiết). Middleware này nằm **trong** CORS nên trình duyệt vẫn đọc được lỗi."""
        try:
            return await call_next(request)
        except Exception:
            logger.exception("unhandled error %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Hệ thống gặp lỗi không mong muốn. Bạn thử lại sau nhé.",
                    "code": "internal_error",
                },
            )
