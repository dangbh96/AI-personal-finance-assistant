"""Schema Budget vs Actual (Phase 5). Tiền là số nguyên đồng (ADR-007); tỉ lệ là số thực."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import AllocationGroup, BudgetStatus, BudgetStrategy, SpendingType
from app.schemas.category import CategoryBrief
from app.schemas.zone import AllocationZoneRead, AutoZoneDetailRead

PaceStatus = Literal["ahead", "on_track", "under"]
AllocationTrackingStatus = Literal["on_track", "ahead_of_pace", "over_budget", "not_tracked"]
ScopeKind = Literal["category", "jar", "group"]


class MonthProgressRead(BaseModel):
    today: date
    date_from: date = Field(description="Ngày đầu tháng")
    date_to: date = Field(description="Ngày cuối tháng")
    elapsed_days: int = Field(description="Số ngày đã qua, tính cả hôm nay (0 nếu tháng chưa tới)")
    days_in_month: int
    month_progress: float = Field(description="elapsed_days / days_in_month (0–1, 4 chữ số)")


class TopContributorRead(BaseModel):
    """Giao dịch lớn nhất của dòng đang vượt, khi nó chiếm ≥ 60% phần vượt."""

    transaction_id: uuid.UUID
    occurred_on: date
    note: str | None
    category: CategoryBrief
    spending_type: SpendingType | None
    amount: int
    overspend: int = Field(description="actual - planned của dòng")
    share: float = Field(description="min(1, amount / overspend), 4 chữ số")


class AllocationScopeRead(BaseModel):
    kind: ScopeKind = Field(
        description="category: theo danh mục · jar: hũ envelope · group: theo spending_type"
    )
    categories: list[CategoryBrief]
    spending_types: list[SpendingType]


class AllocationStatusRead(BaseModel):
    id: uuid.UUID
    position: int
    group: AllocationGroup
    category_id: uuid.UUID | None
    category: CategoryBrief | None
    jar_name: str | None
    scope: AllocationScopeRead
    planned: int
    actual: int = Field(description="Tổng chi khớp dòng trong tháng (nhóm savings luôn 0)")
    variance: int = Field(description="actual - planned (dương = vượt)")
    remaining: int = Field(description="planned - actual (âm = đã vượt)")
    used_percent: float | None = Field(
        description="actual / planned × 100 (1 chữ số); null nếu planned = 0"
    )
    transaction_count: int
    expected_to_date: int = Field(description="planned × month_progress, làm tròn tới đồng")
    pace_status: PaceStatus | None = Field(
        description="So used % với % tháng đã qua, dung sai 10 điểm %; null nếu planned = 0 "
        "hoặc dòng savings"
    )
    status: AllocationTrackingStatus = Field(
        description="over_budget nếu actual > planned; ahead_of_pace nếu pace = ahead; "
        "not_tracked cho nhóm savings (nối Goals/PYF ở Phase 11)"
    )
    top_contributor: TopContributorRead | None
    zone: AllocationZoneRead | None = Field(
        description="Vùng linh hoạt (Phase 9); null với nhóm savings"
    )


class BudgetStatusTotals(BaseModel):
    income_expected: int
    income_actual: int
    income_variance: int = Field(description="income_actual - income_expected")
    expense_planned: int = Field(description="Tổng planned các dòng chi (không gồm savings)")
    expense_actual: int = Field(description="Tổng mọi giao dịch chi trong tháng")
    expense_variance: int = Field(description="expense_actual - expense_planned")
    expense_used_percent: float | None
    allocated_actual: int = Field(description="Tổng actual các dòng phân bổ")
    unbudgeted_actual: int = Field(
        description="Chi tiêu không thuộc dòng phân bổ nào (expense_actual - allocated_actual)"
    )
    savings_planned: int
    net_actual: int = Field(description="income_actual - expense_actual")
    over_budget_count: int


class BudgetStatusRead(BaseModel):
    budget_id: uuid.UUID
    period_month: date
    strategy: BudgetStrategy
    status: BudgetStatus
    progress: MonthProgressRead
    totals: BudgetStatusTotals
    allocations: list[AllocationStatusRead]


class MonthSummaryRead(BaseModel):
    """Thẻ tóm tắt tháng ở trang chủ. Phần `budget` chỉ có khi tháng có budget active/closed."""

    month: date = Field(description="Ngày 1 của tháng")
    progress: MonthProgressRead
    income_actual: int
    expense_actual: int
    net_actual: int
    budget_id: uuid.UUID | None
    budget_status: BudgetStatus | None = Field(description="null nếu tháng chưa có budget")
    budget: BudgetStatusTotals | None
    top_over: AllocationStatusRead | None = Field(description="Dòng vượt nhiều nhất (nếu có)")


class BudgetZoneRead(AllocationZoneRead):
    allocation_id: uuid.UUID
    position: int
    group: AllocationGroup
    category: CategoryBrief | None
    jar_name: str | None
    label: str
    planned: int
    actual: int = Field(description="Tổng chi khớp dòng trong tháng (kể cả khoản bất thường)")
    used_percent: float | None
    expected_to_date: int = Field(description="planned × % tháng đã qua (pro-rata)")
    auto: AutoZoneDetailRead | None = Field(description="Chỉ có với zone_mode = auto")


class BudgetZoneList(BaseModel):
    """Vùng của mọi dòng chi tiêu (nhóm savings không có vùng)."""

    budget_id: uuid.UUID
    period_month: date
    status: BudgetStatus
    progress: MonthProgressRead
    items: list[BudgetZoneRead]
