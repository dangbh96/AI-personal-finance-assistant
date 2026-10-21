"""Schema cho budget engine (Phase 4). Tiền là số nguyên đồng (ADR-007)."""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import AllocationGroup, BudgetStatus, BudgetStrategy, ZoneMode
from app.schemas.category import CategoryBrief

MAX_MONEY = 10**15

Money = Annotated[int, Field(strict=True, ge=0, le=MAX_MONEY, description="Số nguyên đồng, >= 0")]
JarName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


def _first_day_of_month(value: date) -> date:
    if value.day != 1:
        raise ValueError("Tháng ngân sách phải là ngày 1 của tháng (vd. 2026-10-01)")
    return value


def _optional_first_day_of_month(value: date | None) -> date | None:
    return None if value is None else _first_day_of_month(value)


PeriodMonth = Annotated[date, Field(description="Ngày 1 của tháng, vd. 2026-10-01")]


class BudgetAllocationInput(BaseModel):
    """Một dòng phân bổ: `category_id` **hoặc** `jar_name` (đúng một trong hai).

    - Strategy `envelope`: `jar_name` là tên hũ trong `app_settings.budget_jar_category_map`.
    - Strategy `fifty_thirty_twenty` / `pyf`: dòng theo nhóm có `jar_name` = `group`; actual
      (Phase 5) khớp theo `spending_type` của giao dịch.
    """

    model_config = ConfigDict(extra="forbid")

    group: AllocationGroup
    category_id: uuid.UUID | None = None
    jar_name: JarName | None = None
    planned_amount: Money

    @model_validator(mode="after")
    def _jar_or_category(self) -> "BudgetAllocationInput":
        if (self.category_id is None) == (self.jar_name is None):
            raise ValueError("Mỗi dòng phân bổ cần đúng một trong hai: category_id hoặc jar_name")
        return self


class BudgetAllocationDraft(BaseModel):
    group: AllocationGroup
    category_id: uuid.UUID | None
    category: CategoryBrief | None = None
    jar_name: str | None
    planned_amount: int


class BudgetAllocationRead(BudgetAllocationDraft):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    zone_mode: ZoneMode = Field(description="Vùng linh hoạt (Phase 9): manual | auto")
    comfort_low: int | None = Field(description="null = dòng auto chưa được tính vùng")
    comfort_high: int | None
    warning_threshold: int | None


class GroupTotals(BaseModel):
    essential: int = 0
    wants: int = 0
    savings: int = 0
    irregular: int = 0


class BudgetTotals(BaseModel):
    planned_total: int
    unallocated: int = Field(description="expected_income - planned_total (âm = vượt thu nhập)")
    by_group: GroupTotals


class ReferenceComparison(BaseModel):
    group: AllocationGroup = Field(description="essential | wants | savings")
    planned: int = Field(description="Tổng planned của nhóm (nhóm wants gồm cả irregular)")
    reference: int
    difference: int = Field(description="planned - reference (dương = nhiều hơn tham khảo)")


class FiftyThirtyTwentyReference(BaseModel):
    """50/30/20 chỉ là **tham khảo**, không phải luật."""

    essential: int
    wants: int
    savings: int
    comparison: list[ReferenceComparison]


class BudgetWarning(BaseModel):
    code: str = Field(description="planned_exceeds_income | budget_exists | categories_not_in_jar")
    message: str
    amount: int | None = None


class BudgetRead(BaseModel):
    id: uuid.UUID
    period_month: date
    strategy: BudgetStrategy
    expected_income: int
    savings_target: int | None = Field(description="Tổng planned nhóm savings")
    status: BudgetStatus
    allocations: list[BudgetAllocationRead]
    totals: BudgetTotals
    reference_50_30_20: FiftyThirtyTwentyReference
    created_at: datetime
    updated_at: datetime


class BudgetList(BaseModel):
    items: list[BudgetRead]


class BudgetPreviewRequest(BaseModel):
    """Không gửi `allocations` → tính phân bổ mặc định theo strategy. Có `allocations` (đã chỉnh)
    → chỉ tính lại tổng, cảnh báo, so sánh 50/30/20."""

    model_config = ConfigDict(extra="forbid")

    period_month: PeriodMonth
    strategy: BudgetStrategy
    expected_income: Money
    savings_target: Money | None = Field(default=None, description="Bắt buộc với strategy pyf")
    allocations: list[BudgetAllocationInput] | None = None

    _check_month = field_validator("period_month")(_first_day_of_month)


class BudgetDraft(BaseModel):
    period_month: date
    strategy: BudgetStrategy
    expected_income: int
    savings_target: int
    allocations: list[BudgetAllocationDraft]
    totals: BudgetTotals


class BudgetPreviewResponse(BaseModel):
    budget: BudgetDraft
    reference_50_30_20: FiftyThirtyTwentyReference
    warnings: list[BudgetWarning]


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_month: PeriodMonth
    strategy: BudgetStrategy
    expected_income: Money
    status: BudgetStatus = Field(default="draft", description="draft | active")
    allocations: Annotated[list[BudgetAllocationInput], Field(min_length=1, max_length=100)]
    confirm_over_income: bool = Field(
        default=False, description="Bắt buộc true nếu tổng planned > expected_income"
    )

    _check_month = field_validator("period_month")(_first_day_of_month)


class BudgetUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới cập nhật. `allocations` gửi lên thay thế toàn bộ."""

    model_config = ConfigDict(extra="forbid")

    expected_income: Money = None  # type: ignore[assignment]
    status: BudgetStatus = None  # type: ignore[assignment]
    allocations: Annotated[list[BudgetAllocationInput], Field(min_length=1, max_length=100)] = None  # type: ignore[assignment]
    confirm_over_income: bool = False


class BudgetCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_month: PeriodMonth | None = Field(default=None, description="Mặc định: tháng trước")
    to_month: PeriodMonth

    _check_from = field_validator("from_month")(_optional_first_day_of_month)
    _check_to = field_validator("to_month")(_first_day_of_month)


class BudgetJarRead(BaseModel):
    name: str
    group: AllocationGroup | None = Field(description="Nhóm của hũ trong preset (nếu có)")
    default_percent: int | None = Field(description="% thu nhập mặc định trong preset")
    categories: list[CategoryBrief]


class BudgetJarList(BaseModel):
    items: list[BudgetJarRead]
