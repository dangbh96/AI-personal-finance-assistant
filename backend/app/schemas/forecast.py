"""Schema lịch dòng tiền + dự báo số dư (Phase 12).

Mọi số do `services/forecast_service` tính (deterministic, không AI — ADR-005); tiền là số nguyên
đồng (ADR-007). `ForecastOutput` cũng là output dự kiến cho tool Coach `get_cashflow_forecast`.
"""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Direction
from app.schemas.common import MAX_AMOUNT

CalendarEventKind = Literal["recurring", "paid", "goal_saving"]
ForecastEventKind = Literal["recurring", "goal_saving"]
Balance = Annotated[
    int,
    Field(strict=True, ge=-MAX_AMOUNT, le=MAX_AMOUNT, description="Số nguyên đồng (có thể âm)"),
]
Threshold = Annotated[int, Field(strict=True, ge=0, le=MAX_AMOUNT, description="Đồng, ≥ 0")]
GoalSavingDay = Annotated[int, Field(strict=True, ge=1, le=31)]


# ---------- settings (app_settings.forecast.*) ----------


class ForecastSettings(BaseModel):
    starting_balance: int | None = Field(
        description="Số dư user tự nhập (đồng) — giả định của forecast; null = chưa nhập"
    )
    starting_balance_on: date | None = Field(
        description="Số dư tính tại đầu ngày này; giao dịch từ ngày này trở đi cộng / trừ vào"
    )
    low_balance_threshold: int = Field(description="Cảnh báo khi số dư dự báo < ngưỡng")
    goal_saving_day_of_month: int = Field(description="Ngày đặt khoản để dành cho mục tiêu 🎯")


class ForecastSettingsUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới cập nhật. Gửi `starting_balance` mà không gửi
    `starting_balance_on` → tính từ hôm nay."""

    model_config = ConfigDict(extra="forbid")

    starting_balance: Balance | None = None
    starting_balance_on: date = None  # type: ignore[assignment]
    low_balance_threshold: Threshold = None  # type: ignore[assignment]
    goal_saving_day_of_month: GoalSavingDay = None  # type: ignore[assignment]


# ---------- calendar ----------


class CalendarEvent(BaseModel):
    date: date
    icon: str
    label: str
    amount: int
    direction: Direction
    kind: CalendarEventKind = Field(
        description="recurring = kỳ sắp tới / chưa ghi; paid = giao dịch đã ghi từ khoản định kỳ; "
        "goal_saving = khoản để dành cho mục tiêu (kế hoạch)"
    )
    recurring_id: uuid.UUID | None = None
    transaction_id: uuid.UUID | None = None
    overdue: bool = Field(default=False, description="Kỳ đã qua mà chưa ghi giao dịch")


class CalendarMonth(BaseModel):
    month: date = Field(description="Ngày 1 của tháng")
    today: date
    events: list[CalendarEvent] = Field(description="Theo ngày; trong ngày: thu → chi → mục tiêu")
    income_total: int = Field(description="Tổng thu (kỳ định kỳ + đã ghi) trong tháng")
    expense_total: int = Field(description="Tổng chi (kỳ định kỳ + đã ghi) trong tháng")
    goal_saving_total: int


# ---------- forecast ----------


class ForecastEvent(BaseModel):
    kind: ForecastEventKind
    label: str
    icon: str
    direction: Direction
    amount: int
    recurring_id: uuid.UUID | None = None


class ForecastPoint(BaseModel):
    date: date
    projected_balance: int
    delta_income: int = Field(description="Thu định kỳ đến hạn + thu đã ghi trong ngày")
    delta_expense: int = Field(description="Chi định kỳ đến hạn + chi đã ghi (không gồm biến đổi)")
    delta_goal_saving: int
    delta_variable: int = Field(description="Chi tiêu biến đổi trung bình / ngày")
    events: list[ForecastEvent] = Field(description="Khoản định kỳ / mục tiêu trong ngày")


class OverdueRecurring(BaseModel):
    recurring_id: uuid.UUID
    name: str
    direction: Direction
    amount: int
    due_on: date


class ForecastOutput(BaseModel):
    start_date: date
    days: int
    starting_balance: int = Field(description="Số dư user nhập (0 nếu chưa nhập)")
    starting_balance_on: date | None
    starting_balance_set: bool
    opening_balance: int = Field(
        description="Số dư đầu ngày start_date = starting_balance + giao dịch đã ghi từ "
        "starting_balance_on tới trước start_date"
    )
    low_balance_threshold: int
    points: list[ForecastPoint]
    low_balance_warning_day: date | None = Field(
        description="Ngày đầu tiên số dư dự báo < ngưỡng; null = không có"
    )
    min_balance: int
    min_balance_day: date
    end_balance: int
    average_daily_variable_spending: int = Field(
        description="Chi 30 ngày trước start_date, bỏ khoản định kỳ và bất thường, chia số ngày "
        "có lịch sử (≥ 7); thiếu → 0"
    )
    variable_history_days: int
    insufficient_history: bool = Field(description="Lịch sử < 30 ngày → số trung bình kém tin cậy")
    monthly_goal_saving: int = Field(description="Tổng gợi ý để dành / tháng của mục tiêu active")
    goal_saving_day_of_month: int
    recurring_income_total: int
    recurring_expense_total: int
    goal_saving_total: int
    variable_spending_total: int
    overdue_recurring: list[OverdueRecurring] = Field(
        description="Kỳ đã quá hạn chưa ghi giao dịch — không tính vào dự báo"
    )
