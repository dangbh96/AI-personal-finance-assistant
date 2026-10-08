"""Lỗi nghiệp vụ và handler trả về dạng `{"detail": ..., "code": ...}`."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 422

    def __init__(self, detail: str, code: str = "invalid") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class NotFoundError(DomainError):
    status_code = 404

    def __init__(self, detail: str, code: str = "not_found") -> None:
        super().__init__(detail, code)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
        )
