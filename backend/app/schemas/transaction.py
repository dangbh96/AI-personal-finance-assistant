import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import Direction, SpendingType, TransactionSource
from app.schemas.category import CategoryBrief
from app.schemas.classification import PreferenceRead
from app.schemas.common import MAX_AMOUNT
from app.schemas.goal import PyfProposal

Amount = Annotated[int, Field(strict=True, gt=0, le=MAX_AMOUNT, description="Số nguyên đồng, > 0")]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Direction
    amount: Amount
    occurred_on: date
    category_id: uuid.UUID
    spending_type: SpendingType | None = Field(
        default=None,
        description="Chỉ cho expense; bỏ trống thì dùng default_spending_type của category",
    )
    note: Note | None = None
    source: TransactionSource = "manual"
    raw_input: Annotated[str, StringConstraints(max_length=2000)] | None = None
    ai_suggestion: dict[str, Any] | None = None

    _normalize_note = field_validator("note", mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def _income_has_no_spending_type(self) -> "TransactionCreate":
        if self.direction == "income" and self.spending_type is not None:
            raise ValueError("Thu nhập không có loại chi tiêu (spending_type phải null)")
        return self


class TransactionUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới được cập nhật; ràng buộc kiểm tra trên trạng thái đã gộp."""

    model_config = ConfigDict(extra="forbid")

    # Không nhận null cho các field bắt buộc (mặc định None chỉ để biểu thị "không gửi").
    direction: Direction = None  # type: ignore[assignment]
    amount: Amount = None  # type: ignore[assignment]
    occurred_on: date = None  # type: ignore[assignment]
    category_id: uuid.UUID = None  # type: ignore[assignment]
    spending_type: SpendingType | None = None
    note: Note | None = None

    _normalize_note = field_validator("note", mode="before")(_blank_to_none)


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: Direction
    amount: int
    occurred_on: date
    note: str | None
    category_id: uuid.UUID
    category: CategoryBrief
    spending_type: SpendingType | None
    source: TransactionSource
    raw_input: str | None
    ai_suggestion: dict[str, Any] | None
    recurring_id: uuid.UUID | None = Field(
        default=None, description="Khoản định kỳ đã sinh / gắn giao dịch này (Phase 12)"
    )
    receipt_id: uuid.UUID | None = Field(
        default=None, description="Ảnh hoá đơn đã tạo giao dịch này (Phase 13)"
    )
    import_batch_id: uuid.UUID | None = Field(
        default=None, description="Lô import sao kê đã tạo giao dịch này (Phase 14)"
    )
    created_at: datetime
    updated_at: datetime


class TransactionCreateResult(TransactionRead):
    """Kết quả `POST /transactions`: giao dịch + preference vừa học (nếu user đã sửa đề xuất AI)
    + đề xuất Pay Yourself First (Phase 11) khi là thu nhập."""

    learned_preference: PreferenceRead | None = None
    pyf_proposal: PyfProposal | None = Field(
        default=None,
        description="Chỉ với thu nhập, khi có goal active hoặc ngân sách tháng dùng strategy pyf. "
        "Chưa ghi gì — user xác nhận qua POST /goals/allocations",
    )


class TransactionList(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int


class SpendingTypeTotals(BaseModel):
    essential: int = 0
    non_essential: int = 0
    irregular: int = 0


class CategoryTotal(BaseModel):
    category_id: uuid.UUID
    name: str
    kind: Direction
    icon: str | None
    total: int


class TransactionSummary(BaseModel):
    date_from: date | None
    date_to: date | None
    income_total: int
    expense_total: int
    net: int = Field(description="income_total - expense_total (có thể âm)")
    by_spending_type: SpendingTypeTotals
    by_category: list[CategoryTotal]
