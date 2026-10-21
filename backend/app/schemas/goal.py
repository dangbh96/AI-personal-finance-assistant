"""Schema Goals + Pay Yourself First (Phase 11).

Mọi số (`current_amount`, `remaining_amount`, `months_remaining`, `suggested_monthly_saving`,
`available_spending`…) do `services/goal_service` tính (deterministic, ADR-005). Tiền là số nguyên
đồng (ADR-007).
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import BudgetStatus, BudgetStrategy, GoalStatus
from app.schemas.common import MAX_AMOUNT

GoalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
GoalAmount = Annotated[
    int, Field(strict=True, gt=0, le=MAX_AMOUNT, description="Số nguyên đồng, > 0")
]
AllocationAmount = Annotated[
    int, Field(strict=True, ge=0, le=MAX_AMOUNT, description="Số nguyên đồng, ≥ 0 (0 = bỏ qua)")
]
Priority = Annotated[int, Field(strict=True, ge=1, le=100, description="1 = ưu tiên cao nhất")]
MAX_ALLOCATION_ITEMS = 50


# ---------- goal ----------


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: GoalName
    target_amount: GoalAmount
    deadline: date = Field(description="Hạn đạt mục tiêu (không được ở quá khứ)")
    priority: Priority = 1


class GoalUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới cập nhật."""

    model_config = ConfigDict(extra="forbid")

    name: GoalName = None  # type: ignore[assignment]
    target_amount: GoalAmount = None  # type: ignore[assignment]
    deadline: date = None  # type: ignore[assignment]
    priority: Priority = None  # type: ignore[assignment]
    status: GoalStatus = None  # type: ignore[assignment]


class GoalRead(BaseModel):
    id: uuid.UUID
    name: str
    target_amount: int
    current_amount: int = Field(description="Tổng các khoản góp")
    remaining_amount: int = Field(description="max(0, target_amount - current_amount)")
    progress_pct: float = Field(description="current / target × 100 (1 chữ số, tối đa 100)")
    deadline: date
    months_remaining: int = Field(
        description="Số tháng còn lại tính cả tháng hiện tại, không tính tháng đến hạn; tối thiểu "
        "1 nếu chưa quá hạn; 0 nếu đã quá hạn"
    )
    suggested_monthly_saving: int = Field(
        description="remaining / months_remaining làm tròn lên bội số 100.000 (không vượt "
        "remaining); quá hạn → toàn bộ remaining; đã đạt → 0"
    )
    on_track: bool = Field(
        description="Đã đạt, hoặc chưa quá hạn và current + suggested × months ≥ target"
    )
    overdue: bool = Field(description="Đã quá hạn mà chưa đạt")
    priority: int
    status: GoalStatus
    contribution_count: int
    last_contributed_on: date | None
    created_at: datetime
    updated_at: datetime


class GoalList(BaseModel):
    items: list[GoalRead] = Field(
        description="Đang thực hiện → tạm dừng → đã đạt; trong nhóm theo priority, deadline"
    )
    total_suggested_monthly_saving: int = Field(description="Tổng gợi ý/tháng của goal active")


class IncomeBrief(BaseModel):
    id: uuid.UUID
    amount: int
    occurred_on: date
    note: str | None
    category_name: str


class GoalContributionRead(BaseModel):
    id: uuid.UUID
    goal_id: uuid.UUID
    amount: int
    contributed_on: date
    income_transaction_id: uuid.UUID | None = Field(description="null = góp thủ công")
    income_transaction: IncomeBrief | None
    created_at: datetime


class GoalDetail(BaseModel):
    goal: GoalRead
    contributions: list[GoalContributionRead] = Field(description="Mới nhất trước")


class GoalContributionCreate(BaseModel):
    """Khoản góp thủ công (không gắn thu nhập), vd số tiền đã để dành sẵn."""

    model_config = ConfigDict(extra="forbid")

    amount: GoalAmount
    contributed_on: date | None = Field(default=None, description="Mặc định hôm nay")


# ---------- Pay Yourself First ----------


class PyfAllocationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: uuid.UUID
    amount: AllocationAmount


class PyfProposalRequest(BaseModel):
    """Tính đề xuất PYF cho một thu nhập đã lưu. **Không ghi DB.**

    Không gửi `items` → đề xuất mặc định theo priority. Gửi `items` (số user đã chỉnh) → tính lại
    phần còn thiếu / số còn lại để chi tiêu và cảnh báo (goal không có trong `items` = 0).
    """

    model_config = ConfigDict(extra="forbid")

    income_transaction_id: uuid.UUID
    items: (
        Annotated[list[PyfAllocationItemInput], Field(max_length=MAX_ALLOCATION_ITEMS)] | None
    ) = None
    budget_savings_amount: AllocationAmount | None = Field(
        default=None, description="Bỏ trống → min(savings_target, phần thu nhập còn lại)"
    )


class PyfProposalItem(BaseModel):
    goal_id: uuid.UUID
    name: str
    priority: int
    deadline: date
    months_remaining: int
    current_amount: int
    remaining_amount: int
    suggested_monthly_saving: int
    proposed_amount: int = Field(description="min(gợi ý/tháng, còn thiếu, thu nhập còn lại)")
    amount: int = Field(description="Số sẽ ghi khi xác nhận (= proposed_amount nếu chưa chỉnh)")
    remaining_after: int = Field(description="remaining_amount - amount (âm = góp quá)")
    exceeds_remaining: bool


class PyfWarning(BaseModel):
    code: str = Field(description="allocation_exceeds_income | allocation_exceeds_remaining")
    message: str
    amount: int | None = None


class PyfProposal(BaseModel):
    income_transaction_id: uuid.UUID
    income: IncomeBrief
    income_amount: int
    budget_month: date
    budget_id: uuid.UUID | None
    budget_strategy: BudgetStrategy | None
    budget_status: BudgetStatus | None
    budget_savings_target: int | None = Field(
        description="savings_target của ngân sách tháng thu nhập; null = tháng chưa có ngân sách"
    )
    items: list[PyfProposalItem] = Field(description="Goal active theo priority")
    goal_total: int
    budget_savings_amount: int
    allocated_total: int = Field(description="goal_total + budget_savings_amount")
    available_spending: int = Field(
        description="income_amount - goal_total - budget_savings_amount (âm = phân bổ quá thu nhập)"
    )
    warnings: list[PyfWarning]
    valid: bool = Field(description="false nếu có cảnh báo chặn xác nhận")


class PyfAllocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    income_transaction_id: uuid.UUID
    items: Annotated[list[PyfAllocationItemInput], Field(max_length=MAX_ALLOCATION_ITEMS)] = Field(
        default_factory=list
    )
    budget_savings_amount: AllocationAmount = Field(
        default=0, description="Khoản tiết kiệm chưa gắn goal (không lưu thành bản ghi riêng)"
    )


class PyfAllocationResult(BaseModel):
    income_transaction_id: uuid.UUID
    income_amount: int
    contributions: list[GoalContributionRead]
    goal_total: int
    budget_savings_amount: int
    available_spending: int = Field(
        description="income_amount - goal_total - budget_savings_amount"
    )
    goals: list[GoalRead] = Field(description="Các goal vừa nhận tiền (đã cập nhật)")


class UnallocatedIncomeList(BaseModel):
    items: list[IncomeBrief] = Field(
        description="Thu nhập từ đầu tháng trước tới hôm nay chưa có khoản góp nào, mới nhất trước"
    )
