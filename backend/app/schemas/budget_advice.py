"""Schema Budget adjustment advisor (Phase 8). Tiền là số nguyên đồng (ADR-007).

`verdict` + `evidence` do `services/advisor_rules` tính (deterministic, ADR-005); AI chỉ viết
`BudgetAdviceExplanation` từ evidence. Tỉ lệ dạng `0..1` có 4 chữ số; `*_pct` là phần trăm 1 chữ
số (để văn bản trích dẫn được mà không phải tự tính).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import (
    AdviceStatus,
    AdviceVerdict,
    AllocationGroup,
    BudgetStatus,
    SpendingType,
)
from app.schemas.budget import BudgetAllocationRead, PeriodMonth
from app.schemas.category import CategoryBrief
from app.schemas.zone import ZoneEvidence

AdviceRule = Literal[
    "within_plan",
    "one_off_irregular",
    "one_off_single_transaction",
    "insufficient_history",
    "stable_overspend",
    "unstable_overspend",
]
AdviceTone = Literal["neutral", "supportive"]
AdviceTextSource = Literal["ai", "template"]

MAX_DISMISS_REASON_LENGTH = 500


def _first_day_of_month(value: date | None) -> date | None:
    if value is not None and value.day != 1:
        raise ValueError("Tháng phải là ngày 1 của tháng (vd. 2026-10-01)")
    return value


# ---------- thresholds (app_settings.budget_advisor) ----------


class AdvisorSettings(BaseModel):
    """Ngưỡng decision tree (docs/architecture/budget-adjustment.md § 1)."""

    one_off_share_threshold: float = Field(
        gt=0,
        le=1,
        description="Giao dịch bất thường / đơn lẻ chiếm ≥ tỉ lệ này phần vượt → one_off",
    )
    stable_cv_threshold: float = Field(
        gt=0, le=1, description="CV (population std / mean) của actual ≤ ngưỡng → ổn định"
    )
    min_history_months: int = Field(ge=2, le=12, description="Số tháng lịch sử tối thiểu")
    budget_rounding_step: int = Field(
        ge=1_000, le=10_000_000, description="Bước làm tròn planned đề xuất (đồng)"
    )


class AdvisorSettingsUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới cập nhật."""

    model_config = ConfigDict(extra="forbid")

    one_off_share_threshold: float = Field(default=None, gt=0, le=1)  # type: ignore[assignment]
    stable_cv_threshold: float = Field(default=None, gt=0, le=1)  # type: ignore[assignment]
    min_history_months: int = Field(default=None, ge=2, le=12)  # type: ignore[assignment]
    budget_rounding_step: int = Field(default=None, ge=1_000, le=10_000_000)  # type: ignore[assignment]


# ---------- evidence ----------


class AdviceTransaction(BaseModel):
    transaction_id: uuid.UUID
    occurred_on: date
    note: str | None
    amount: int
    category_name: str
    spending_type: SpendingType | None


class AdviceHistoryMonth(BaseModel):
    month: date
    actual: int = Field(description="Tổng chi trong phạm vi dòng phân bổ của tháng")
    transaction_count: int
    has_data: bool = Field(description="Tháng có ít nhất 1 giao dịch chi trong phạm vi")
    over_planned: bool = Field(description="actual > planned_amount (của tháng đang xét)")


class BudgetAdviceEvidence(BaseModel):
    """Số liệu deterministic làm căn cứ cho verdict — nguồn số duy nhất của explanation."""

    allocation_label: str
    group: AllocationGroup
    category_slug: str | None
    month: date
    as_of: date = Field(description="Ngày tính số liệu (≤ cuối tháng)")
    month_complete: bool
    planned_amount: int
    actual_amount: int
    variance: int = Field(description="actual_amount - planned_amount")
    comfort_high: int | None = Field(description="Ngưỡng trên vùng an toàn (Phase 9), nếu có")
    comfort_high_used: bool = Field(description="true nếu so với comfort_high thay vì planned")
    threshold_amount: int = Field(description="comfort_high nếu có, ngược lại planned_amount")
    over_amount: int = Field(description="max(0, actual_amount - threshold_amount)")
    transaction_count: int
    largest_transaction: AdviceTransaction | None
    single_transaction_share: float | None = Field(
        description="Giao dịch lớn nhất / phần vượt (tối đa 1); null nếu không vượt"
    )
    single_transaction_share_pct: float | None
    irregular_total: int = Field(description="Tổng giao dịch spending_type = irregular")
    irregular_share: float | None = Field(
        description="irregular_total / phần vượt (tối đa 1); null nếu không vượt"
    )
    irregular_share_pct: float | None
    irregular_transaction: AdviceTransaction | None = Field(
        description="Giao dịch bất thường lớn nhất (nếu có)"
    )
    one_off_transaction: AdviceTransaction | None = Field(
        description="Giao dịch ngoại lệ được chỉ ra khi verdict = one_off"
    )
    history_actuals: list[AdviceHistoryMonth] = Field(
        description="min_history_months tháng gần nhất, tính cả tháng đang xét, cũ nhất trước"
    )
    history_months: int = Field(description="Số tháng trong history_actuals có dữ liệu")
    min_history_months: int
    all_over_planned: bool = Field(description="Mọi tháng trong history_actuals đều vượt planned")
    cv: float | None = Field(description="Population std / mean của history_actuals (4 chữ số)")
    cv_pct: float | None
    history_median: int | None
    proposed_planned_amount: int | None = Field(
        description="Chỉ khi verdict = adjust_budget: median làm tròn budget_rounding_step"
    )
    one_off_share_threshold_pct: float
    stable_cv_threshold_pct: float
    budget_rounding_step: int
    rule: AdviceRule = Field(description="Nhánh của decision tree dẫn tới verdict")
    zone: ZoneEvidence | None = Field(
        default=None,
        description="Vùng linh hoạt (Phase 9) của dòng trong tháng xét, nếu dòng đã có ngưỡng",
    )


# ---------- văn bản ----------


class BudgetAdviceExplanation(BaseModel):
    """Structured output của model — 3 tầng Observation → Explanation → Action."""

    observation: str = Field(description="Nêu planned/actual/variance từ evidence")
    explanation: str = Field(description="Giải thích verdict, không thêm số ngoài evidence")
    action: str | None = Field(description="Gợi ý có điều kiện; accept/dismiss do user quyết")
    tone: AdviceTone


class AdviceNarrative(BudgetAdviceExplanation):
    generated_by: AdviceTextSource = Field(description="ai | template (không dùng AI)")
    fallback_reason: str | None = Field(
        default=None,
        description="Mã lý do dùng template khi AI lỗi: AI_NOT_CONFIGURED, AI_INVALID_OUTPUT…; "
        "null nếu dùng AI hoặc template theo thiết kế (verdict on_track)",
    )


# ---------- API ----------


class BudgetAdviceRead(BaseModel):
    id: uuid.UUID
    budget_allocation_id: uuid.UUID
    budget_id: uuid.UUID
    month: date
    allocation_label: str
    group: AllocationGroup
    category: CategoryBrief | None
    jar_name: str | None
    verdict: AdviceVerdict
    evidence: BudgetAdviceEvidence
    explanation: str
    narrative: AdviceNarrative | None
    model: str | None = Field(description="Tên model AI, `template` hoặc `fallback_template`")
    status: AdviceStatus
    applied_month: date | None = Field(description="Tháng đã áp dụng planned mới (accepted)")
    dismiss_reason: str | None
    created_at: datetime
    updated_at: datetime


class BudgetAdviceList(BaseModel):
    items: list[BudgetAdviceRead]


class BudgetAdviceGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: PeriodMonth
    allocation_id: uuid.UUID | None = Field(
        default=None, description="Chỉ tạo cho 1 dòng phân bổ của tháng; null = mọi dòng"
    )
    regenerate: bool = Field(
        default=False, description="true → tính lại advice đang open (gọi lại AI)"
    )
    today: date | None = Field(default=None, description="Hôm nay phía user (mặc định server)")

    _check_month = field_validator("month")(_first_day_of_month)


class BudgetAdviceAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = Field(default=False, description="Bắt buộc true — user xác nhận áp dụng")
    target_month: PeriodMonth | None = Field(
        default=None, description="Tháng áp dụng (mặc định tháng sau tháng của advice)"
    )
    confirm_over_income: bool = Field(
        default=False, description="Bắt buộc true nếu planned mới làm tổng vượt thu nhập dự kiến"
    )

    _check_month = field_validator("target_month")(_first_day_of_month)


class BudgetAdviceDismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, max_length=MAX_DISMISS_REASON_LENGTH),
        ]
        | None
    ) = None


class AppliedBudgetRead(BaseModel):
    id: uuid.UUID
    period_month: date
    status: BudgetStatus
    created: bool = Field(description="true nếu vừa tạo nháp (copy từ tháng của advice)")


class BudgetAdviceAcceptResult(BaseModel):
    advice: BudgetAdviceRead
    updated_allocation: BudgetAllocationRead
    budget: AppliedBudgetRead
