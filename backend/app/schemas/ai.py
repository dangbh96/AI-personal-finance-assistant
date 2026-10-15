"""Schema cho các tác vụ AI. Endpoint AI chỉ trả draft, không ghi DB (ADR-005)."""

import uuid
from datetime import date
from typing import Annotated, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import Direction, SpendingType
from app.schemas.transaction import MAX_AMOUNT

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
MAX_DRAFTS = 10


class _DraftFields(BaseModel):
    direction: Direction
    amount: int = Field(gt=0, le=MAX_AMOUNT, description="Số nguyên đồng (VND), > 0")
    occurred_on: date
    note: str = Field(max_length=500, description="Mô tả ngắn, tiếng Việt")
    category_slug: str = Field(description="Slug thuộc danh sách danh mục gửi kèm")
    spending_type: SpendingType | None = Field(description="Chỉ cho expense; income phải là null")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=500, description="Vì sao chọn danh mục / loại chi tiêu")

    @model_validator(mode="after")
    def _spending_type_matches_direction(self) -> Self:
        if self.direction == "income" and self.spending_type is not None:
            raise ValueError("income phải có spending_type = null")
        if self.direction == "expense" and self.spending_type is None:
            raise ValueError(
                "expense phải có spending_type là essential | non_essential | irregular"
            )
        return self


class TransactionDraftOutput(_DraftFields):
    """Một giao dịch do model trả về (structured output)."""


class TransactionParseOutput(BaseModel):
    """Structured output của model cho tác vụ parse câu nhập giao dịch."""

    transactions: list[TransactionDraftOutput] = Field(min_length=1, max_length=MAX_DRAFTS)
    warnings: list[str] = Field(
        max_length=5, description="Điểm mơ hồ user cần kiểm tra, tiếng Việt; rỗng nếu không có"
    )


class TransactionDraft(_DraftFields):
    """Draft gửi cho frontend: như output của model + `category_id` đã resolve."""

    category_id: uuid.UUID


class TransactionParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    today: date | None = Field(
        default=None, description="Ngày hiện tại phía user; bỏ trống thì lấy theo `timezone`"
    )
    timezone: str = DEFAULT_TIMEZONE

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Múi giờ không hợp lệ: {value}") from exc
        return value


class TransactionParseResponse(BaseModel):
    drafts: list[TransactionDraft]
    model: str
    raw_input: str
    warnings: list[str]
