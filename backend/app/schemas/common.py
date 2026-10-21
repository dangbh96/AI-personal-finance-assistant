from typing import Any

from pydantic import BaseModel

# Giới hạn số tiền nhận từ API (đồng).
MAX_AMOUNT = 10**15


class ErrorResponse(BaseModel):
    detail: str | list[dict[str, Any]]
    code: str
