"""Schema khoản định kỳ + phát hiện định kỳ (Phase 12).

Lịch đến hạn (`next_due_on`), trạng thái đến hạn và đề xuất phát hiện từ lịch sử do
`services/recurring_service` / `recurring_detection` tính (deterministic, ADR-005). Tiền là số
nguyên đồng (ADR-007).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import Direction, RecurringFrequency, SpendingType
from app.schemas.category import CategoryBrief
from app.schemas.common import MAX_AMOUNT
from app.schemas.goal import PyfProposal
from app.schemas.transaction import TransactionRead

RecurringName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
RecurringAmount = Annotated[
    int, Field(strict=True, gt=0, le=MAX_AMOUNT, description="Số nguyên đồng, > 0")
]
DayOfMonth = Annotated[
    int, Field(strict=True, ge=1, le=31, description="1–31; 31 → ngày cuối ở tháng ngắn")
]
DayOfWeek = Annotated[int, Field(strict=True, ge=1, le=7, description="ISO: Thứ Hai = 1")]
DueStatus = Literal["overdue", "due_today", "upcoming", "later"]


class RecurringCreate(BaseModel):
    """Tạo khoản định kỳ thủ công.

    - `weekly`: `day_of_week` (hoặc suy từ `next_due_on`).
    - `monthly`: `day_of_month` (hoặc suy từ `next_due_on`).
    - `yearly`: bắt buộc `next_due_on` (lấy tháng); `day_of_month` mặc định ngày của nó.
    - Bỏ trống `next_due_on` → kỳ đầu tiên **sau** hôm nay.
    """

    model_config = ConfigDict(extra="forbid")

    name: RecurringName
    direction: Direction
    amount: RecurringAmount
    category_id: uuid.UUID
    spending_type: SpendingType | None = Field(
        default=None,
        description="Chỉ cho expense; bỏ trống thì dùng default_spending_type của category",
    )
    frequency: RecurringFrequency
    day_of_month: DayOfMonth | None = None
    day_of_week: DayOfWeek | None = None
    next_due_on: date | None = None


class RecurringUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới cập nhật. Đổi lịch mà không gửi `next_due_on` → tính lại kỳ
    đầu tiên sau hôm nay. Bật lại (`active: true`) khoản đã quá hạn → nhảy tới kỳ sau hôm nay."""

    model_config = ConfigDict(extra="forbid")

    name: RecurringName = None  # type: ignore[assignment]
    direction: Direction = None  # type: ignore[assignment]
    amount: RecurringAmount = None  # type: ignore[assignment]
    category_id: uuid.UUID = None  # type: ignore[assignment]
    spending_type: SpendingType | None = None
    frequency: RecurringFrequency = None  # type: ignore[assignment]
    day_of_month: DayOfMonth | None = None
    day_of_week: DayOfWeek | None = None
    next_due_on: date = None  # type: ignore[assignment]
    active: bool = None  # type: ignore[assignment]


class RecurringRead(BaseModel):
    id: uuid.UUID
    name: str
    direction: Direction
    amount: int
    category_id: uuid.UUID
    category: CategoryBrief
    spending_type: SpendingType | None
    frequency: RecurringFrequency
    day_of_month: int | None
    day_of_week: int | None
    next_due_on: date
    auto_detected: bool
    active: bool
    icon: str = Field(description="Icon lịch: 💰 thu nhập, 🏠 nhà, 💳 thẻ tín dụng, 📱 tiện ích…")
    days_until_due: int = Field(description="next_due_on - hôm nay (âm = quá hạn)")
    due_status: DueStatus = Field(
        description="overdue (< hôm nay) | due_today | upcoming (≤ 14 ngày) | later"
    )
    transaction_count: int = Field(description="Số giao dịch đã gắn khoản định kỳ này")
    created_at: datetime
    updated_at: datetime


class RecurringList(BaseModel):
    items: list[RecurringRead] = Field(
        description="Đang bật trước, theo next_due_on (gần nhất trước)"
    )


class RecurringTransactionCreate(BaseModel):
    """Ghi kỳ đang đến hạn thành giao dịch thật (`source = 'recurring'`)."""

    model_config = ConfigDict(extra="forbid")

    occurred_on: date | None = Field(default=None, description="Mặc định min(next_due_on, hôm nay)")
    amount: RecurringAmount | None = Field(
        default=None, description="Số tiền thực tế kỳ này; mặc định số của khoản định kỳ"
    )


class RecurringTransactionResult(BaseModel):
    transaction: TransactionRead
    recurring: RecurringRead = Field(description="Khoản định kỳ đã chuyển sang kỳ sau")
    pyf_proposal: PyfProposal | None = Field(
        default=None,
        description="Đề xuất Pay Yourself First khi là thu nhập (như POST /transactions)",
    )


# ---------- phát hiện định kỳ ----------


class RecurringDetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date | None = Field(default=None, description="Mặc định to_date − 180 ngày")
    to_date: date | None = Field(default=None, description="Mặc định hôm nay")


class RecurringSuggestion(BaseModel):
    id: uuid.UUID = Field(description="Ổn định theo (chiều, danh mục, loại chi, tần suất, ngày)")
    name: str
    direction: Direction
    amount: int = Field(description="Trung vị số tiền các lần xuất hiện")
    category_id: uuid.UUID
    category_name: str
    spending_type: SpendingType | None
    frequency: RecurringFrequency
    day_of_month: int | None
    day_of_week: int | None
    next_due_on: date = Field(description="Kỳ đầu tiên sau max(lần cuối, hôm nay)")
    icon: str
    confidence: float = Field(
        description="0.4 + amount_consistency × 0.3 + interval_consistency × 0.3 (≥ 0.75)"
    )
    amount_consistency: float = Field(
        description="1 − (độ lệch trung bình so với trung vị) / 10%, trong [0, 1]"
    )
    interval_consistency: float = Field(description="Tỉ lệ khoảng cách đúng nhịp tuần / tháng")
    median_interval_days: float
    occurrences: int
    first_occurred_on: date
    last_occurred_on: date
    amounts: list[int] = Field(description="Số tiền các lần xuất hiện (cũ nhất trước)")
    transaction_ids: list[uuid.UUID]


class RecurringSuggestionList(BaseModel):
    from_date: date | None
    to_date: date | None
    suggestions: list[RecurringSuggestion] = Field(
        description="Chưa tạo gì — user xác nhận qua …/suggestions/{id}/confirm"
    )


class RecurringSuggestionConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RecurringName | None = None
    amount: RecurringAmount | None = None
    next_due_on: date | None = None
