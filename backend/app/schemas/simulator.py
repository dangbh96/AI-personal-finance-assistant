"""What-if simulator (Phase 17). Mọi số là số nguyên đồng / tháng (ADR-007); 1 tháng = 30 ngày."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import MAX_AMOUNT

MAX_PARAMS = 10
MAX_INCOME_DELTA = 10_000_000_000

ScenarioName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class ReduceCategoryParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reduce_category"]
    category_id: uuid.UUID
    percent: int = Field(gt=0, le=100, description="Giảm bao nhiêu % chi tiêu trung bình / tháng")


class ChangeIncomeParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["change_income"]
    delta_amount: int = Field(
        ge=-MAX_INCOME_DELTA,
        le=MAX_INCOME_DELTA,
        description="Thu nhập / tháng tăng (+) / giảm (−)",
    )


class AddRecurringExpenseParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["add_recurring_expense"]
    name: ScenarioName
    amount: int = Field(gt=0, le=MAX_AMOUNT, description="Số tiền mỗi tháng")
    category_id: uuid.UUID


class ChangeGoalDeadlineParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["change_goal_deadline"]
    goal_id: uuid.UUID
    new_deadline: date


ScenarioParam = Annotated[
    ReduceCategoryParam | ChangeIncomeParam | AddRecurringExpenseParam | ChangeGoalDeadlineParam,
    Field(discriminator="type"),
]


class SimulationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    params: list[ScenarioParam] = Field(min_length=1, max_length=MAX_PARAMS)
    baseline_months: int = Field(
        default=3, ge=1, le=12, description="Số tháng đã trọn gần nhất dùng làm mức nền"
    )
    include_irregular: bool = Field(
        default=False, description="Tính cả khoản chi bất thường (một lần) vào mức nền"
    )


class SimulationRequest(SimulationOptions):
    start_date: date | None = Field(
        default=None, description="Ngày bắt đầu tính tiến độ mục tiêu (mặc định hôm nay)"
    )
    with_narrative: bool = Field(default=False, description="Viết diễn giải 3 tầng (AI / mẫu)")


# ---------- kết quả ----------


class AppliedParam(BaseModel):
    index: int
    type: str
    label: str = Field(description="Mô tả tiếng Việt, vd 'Giảm Ăn uống 20%'")
    percent: int | None = None
    amount: int | None = Field(default=None, description="Số tiền tham số (thu nhập / khoản mới)")
    delta_monthly_savings: int = Field(
        description="Tiết kiệm / tháng thay đổi do riêng tham số này"
    )


class SimulationCategoryChange(BaseModel):
    category_id: uuid.UUID | None
    name: str
    baseline: int
    projected: int
    delta: int = Field(description="projected − baseline")


class GoalImpact(BaseModel):
    goal_id: uuid.UUID
    name: str
    priority: int
    remaining_amount: int
    deadline_before: date
    deadline_after: date
    months_before: float | None = Field(description="Số tháng để đạt (2 chữ số); null = không đạt")
    months_after: float | None
    days_before: int | None = Field(description="Số ngày để đạt (1 tháng = 30 ngày, làm tròn lên)")
    days_after: int | None
    completion_date_before: date | None
    completion_date_after: date | None
    days_earlier: int | None = Field(description="days_before − days_after (dương = sớm hơn)")
    required_monthly_before: int = Field(description="Cần để dành / tháng để kịp hạn cũ")
    required_monthly_after: int = Field(description="Cần để dành / tháng để kịp hạn mới")
    on_track_before: bool = Field(description="Ngày hoàn thành ≤ hạn")
    on_track_after: bool


class BudgetVarianceImpact(BaseModel):
    label: str
    planned: int
    baseline_actual: int = Field(description="Chi trung bình / tháng của dòng (mức nền)")
    projected_actual: int
    variance_before: int = Field(description="baseline_actual − planned (dương = vượt)")
    variance_after: int


class SimulationNarrative(BaseModel):
    observation: str = Field(description="Kịch bản thay đổi gì (số từ kết quả)")
    explanation: str = Field(description="Vì sao (dựa trên kết quả)")
    action: str | None = Field(description="Gợi ý có điều kiện; null nếu không cần")
    caveats: list[str] = Field(description="Giả định / lưu ý (0–3 ý)")


class SimulationResult(BaseModel):
    start_date: date
    baseline_from: date
    baseline_to: date
    baseline_months: int
    include_irregular: bool
    baseline_monthly_income: int
    projected_monthly_income: int
    baseline_monthly_expense: int
    projected_monthly_expense: int
    baseline_monthly_savings: int
    projected_monthly_savings: int
    delta_monthly_savings: int
    applied: list[AppliedParam]
    category_changes: list[SimulationCategoryChange]
    goal_impacts: list[GoalImpact] = Field(description="Mục tiêu đang thực hiện theo priority")
    budget_month: date | None = Field(description="Tháng ngân sách dùng để so (null = không có)")
    budget_variance_after: list[BudgetVarianceImpact]
    warnings: list[str]
    narrative: SimulationNarrative | None = None
    narrative_source: Literal["ai", "template"] | None = None
    narrative_model: str | None = None


# ---------- kịch bản đã lưu ----------


class ScenarioCreate(SimulationOptions):
    name: ScenarioName
    start_date: date | None = None


class ScenarioRead(BaseModel):
    id: uuid.UUID
    name: str
    params: SimulationOptions
    result: SimulationResult
    created_at: datetime
    updated_at: datetime


class ScenarioList(BaseModel):
    items: list[ScenarioRead] = Field(description="Mới nhất trước")
