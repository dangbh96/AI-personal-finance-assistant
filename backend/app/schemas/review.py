"""Schema Weekly review (Phase 6) và Monthly review (Phase 7).

Tiền là số nguyên đồng (ADR-007); `*_change_pct` là phần trăm nguyên (làm tròn half-up), `null`
khi kỳ trước bằng 0; tỉ lệ (`*_pct` dạng float) có 1 chữ số thập phân. Mọi số trong narrative
phải lấy từ metrics (ADR-005).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import (
    AllocationGroup,
    BudgetStatus,
    BudgetStrategy,
    ReviewPeriod,
    ReviewStatus,
    SpendingType,
)
from app.schemas.analytics import AllocationTrackingStatus

TimeBucket = Literal["morning", "noon", "evening"]
NarrativeTone = Literal["neutral", "supportive"]
IncreaseDriver = Literal["irregular", "regular"]

MAX_REFLECTION_LENGTH = 2000
MAX_FLAGGED_TRANSACTIONS = 50
MAX_IRREGULAR_ITEMS = 5
MAX_DIGEST_ANSWER_LENGTH = 300


class SpendingTypeAmounts(BaseModel):
    essential: int
    non_essential: int
    irregular: int


class CategoryChange(BaseModel):
    """Chi tiêu một danh mục kỳ này so với kỳ trước."""

    category_id: uuid.UUID
    slug: str
    name: str
    icon: str | None
    amount: int = Field(description="Tổng chi kỳ này")
    previous_amount: int = Field(description="Tổng chi kỳ trước")
    change: int = Field(description="amount - previous_amount")
    change_pct: int | None = Field(description="change / previous_amount × 100; null nếu = 0")
    transaction_count: int


class PeriodMetrics(BaseModel):
    """Số liệu deterministic của một kỳ (tuần / tháng) so với kỳ liền trước."""

    period: ReviewPeriod
    period_start: date
    period_end: date
    previous_start: date
    previous_end: date
    as_of: date = Field(description="Ngày tính số liệu (≤ period_end)")
    days_elapsed: int = Field(description="Số ngày của kỳ đã qua, tính cả `as_of`")
    days_in_period: int
    complete: bool = Field(description="Kỳ đã kết thúc (days_elapsed = days_in_period)")
    income: int
    expense: int
    net: int = Field(description="income - expense")
    expense_count: int = Field(description="Số giao dịch chi trong kỳ")
    previous_income: int
    previous_expense: int
    expense_change: int = Field(description="expense - previous_expense")
    expense_change_pct: int | None
    by_spending_type: SpendingTypeAmounts
    previous_by_spending_type: SpendingTypeAmounts
    by_category: list[CategoryChange] = Field(
        description="Danh mục chi có phát sinh ở kỳ này hoặc kỳ trước, chi nhiều nhất trước"
    )


class ReviewTransaction(BaseModel):
    id: uuid.UUID
    occurred_on: date
    note: str | None
    amount: int
    category_id: uuid.UUID
    category_slug: str
    category_name: str
    spending_type: SpendingType | None


class RepeatedCluster(BaseModel):
    """Nhóm giao dịch chi lặp lại trong kỳ (cùng danh mục + buổi trong ngày / từ khoá)."""

    key: str
    label: str = Field(description='Vd "Ăn uống buổi tối", "Cà phê"')
    category_id: uuid.UUID
    category_slug: str
    category_name: str
    time_bucket: TimeBucket | None = Field(description="Có giá trị nếu nhóm theo buổi trong ngày")
    count: int
    total: int
    transaction_ids: list[uuid.UUID]


class ReviewHighlights(BaseModel):
    top_categories: list[CategoryChange] = Field(description="Tối đa 3 danh mục chi nhiều nhất")
    top_increase: CategoryChange | None = Field(description="Danh mục tăng nhiều nhất (theo đồng)")
    top_decrease: CategoryChange | None = Field(description="Danh mục giảm nhiều nhất (theo đồng)")
    repeated_clusters: list[RepeatedCluster] = Field(description="Tối đa 3 nhóm, tổng lớn trước")
    top_transactions: list[ReviewTransaction] = Field(description="Tối đa 3 khoản chi lớn nhất")


class ReviewMetrics(PeriodMetrics):
    """Lưu ở `weekly_reviews.metrics`: số liệu kỳ + highlights."""

    highlights: ReviewHighlights


class SpendingTypePercents(BaseModel):
    """Tỉ trọng từng spending type trong tổng chi (%, 1 chữ số); null khi tháng không có chi."""

    essential: float | None
    non_essential: float | None
    irregular: float | None


class BudgetLineSummary(BaseModel):
    """Một dòng phân bổ: planned vs actual cả tháng (từ Budget vs Actual — Phase 5)."""

    allocation_id: uuid.UUID
    label: str = Field(description="Tên danh mục / hũ / nhóm")
    group: AllocationGroup
    planned: int
    actual: int
    variance: int = Field(description="actual - planned (dương = vượt)")
    used_percent: float | None
    status: AllocationTrackingStatus


class MonthlyBudgetSummary(BaseModel):
    """Budget vs actual của tháng (chỉ khi tháng có budget active / closed)."""

    budget_id: uuid.UUID
    status: BudgetStatus
    strategy: BudgetStrategy
    expense_planned: int
    expense_actual: int
    expense_variance: int = Field(description="expense_actual - expense_planned")
    unbudgeted_actual: int = Field(description="Chi tiêu không thuộc dòng phân bổ nào")
    over_budget_count: int
    lines: list[BudgetLineSummary] = Field(description="Theo thứ tự dòng của budget")
    over_lines: list[BudgetLineSummary] = Field(
        description="Tối đa 3 dòng vượt ngân sách, vượt nhiều nhất trước"
    )


class FlaggedTransaction(BaseModel):
    id: uuid.UUID
    occurred_on: date
    note: str | None
    amount: int
    category_name: str
    spending_type: SpendingType | None


class WeeklyReflectionDigest(BaseModel):
    """Một câu trả lời phản tư của review tuần thuộc tháng (tuần có Thứ Hai trong tháng)."""

    reflection_id: uuid.UUID
    weekly_review_id: uuid.UUID
    week_start: date
    question: str
    answer: str = Field(description=f"Tối đa {MAX_DIGEST_ANSWER_LENGTH} ký tự")
    flagged: list[FlaggedTransaction] = Field(
        description='Giao dịch user đánh dấu "không đáng tiền" (bỏ qua giao dịch đã xoá)'
    )


class MonthlyReviewMetrics(ReviewMetrics):
    """Lưu ở `monthly_reviews.metrics`: số liệu tháng (dùng chung với tuần) + phần riêng tháng.

    `saved = income - expense` (có thể âm); `savings_rate_pct = saved / income × 100`
    (1 chữ số, null khi income = 0). "Chi thường xuyên" = chi trừ khoản bất thường.
    """

    saved: int
    savings_rate_pct: float | None
    previous_saved: int
    previous_savings_rate_pct: float | None
    saved_change: int = Field(description="saved - previous_saved")
    income_change: int = Field(description="income - previous_income")
    income_change_pct: int | None
    spending_type_pct: SpendingTypePercents
    regular_expense: int = Field(description="Chi thường xuyên: thiết yếu + không thiết yếu")
    previous_regular_expense: int
    regular_expense_change_pct: int | None
    irregular_change: int = Field(description="Chi bất thường tháng này - tháng trước")
    increase_driver: IncreaseDriver | None = Field(
        description="Khi chi tăng so với tháng trước (có chi): `irregular` nếu chi bất thường "
        "tăng ≥ 50% mức tăng tổng (khoản một lần), ngược lại `regular`; null nếu chi không tăng "
        "hoặc tháng trước không có chi"
    )
    irregular_items: list[ReviewTransaction] = Field(
        description=f"Tối đa {MAX_IRREGULAR_ITEMS} khoản chi bất thường lớn nhất"
    )
    budget: MonthlyBudgetSummary | None
    weekly_reflections: list[WeeklyReflectionDigest] = Field(description="Tuần cũ nhất trước")
    flagged_count: int = Field(description="Số giao dịch khác nhau được đánh dấu trong các tuần")
    flagged_total: int = Field(description="Tổng tiền các giao dịch được đánh dấu")


class ReviewNarrativeOutput(BaseModel):
    """Structured output của model (3 tầng Observation → Explanation → Action)."""

    observation: str = Field(description="What happened — có số liệu copy từ metrics")
    explanation: str = Field(description="Why — nguyên nhân dựa trên highlights")
    notice: list[str] = Field(
        min_length=1, max_length=3, description="What to notice — 1 đến 3 ý ngắn"
    )
    action: str | None = Field(description="Gợi ý có điều kiện ('nếu bạn muốn…'), không ra lệnh")
    reflection_question: str = Field(description="Một câu hỏi phản tư cho user")
    tone: NarrativeTone


class ReviewNarrative(ReviewNarrativeOutput):
    """Lưu ở `weekly_reviews.narrative` / `monthly_reviews.narrative`."""

    fallback_used: bool = Field(description="true nếu là bản tóm tắt tự động (không dùng AI)")
    fallback_reason: str | None = Field(
        default=None,
        description="Mã lý do dùng bản tự động: AI_NOT_CONFIGURED, AI_TIMEOUT…, validation_failed",
    )


class ReflectionAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_kind: Literal["weekly", "monthly"]
    review_id: uuid.UUID
    question: str
    answer: str
    flagged_transaction_ids: list[uuid.UUID]
    created_at: datetime


class WeeklyReviewRead(BaseModel):
    id: uuid.UUID
    week_start: date
    week_end: date
    metrics: ReviewMetrics
    narrative: ReviewNarrative
    model: str | None = Field(
        description="Model AI đã viết narrative; `fallback_template` nếu dùng bản tự động"
    )
    status: ReviewStatus
    reflections: list[ReflectionAnswerRead] = Field(description="Cũ nhất trước")
    created_at: datetime
    updated_at: datetime


class WeeklyReviewList(BaseModel):
    items: list[WeeklyReviewRead]


class MonthlyReviewRead(BaseModel):
    id: uuid.UUID
    month: date = Field(description="Ngày 1 của tháng")
    month_end: date
    metrics: MonthlyReviewMetrics
    narrative: ReviewNarrative
    model: str | None = Field(
        description="Model AI đã viết narrative; `fallback_template` nếu dùng bản tự động"
    )
    status: ReviewStatus
    reflections: list[ReflectionAnswerRead] = Field(description="Cũ nhất trước")
    created_at: datetime
    updated_at: datetime


class MonthlyReviewList(BaseModel):
    items: list[MonthlyReviewRead]


class MonthlyReviewGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: date = Field(description="Ngày 1 của tháng")
    regenerate: bool = Field(
        default=False,
        description="true: tạo lại narrative/metrics cho review đã có (giữ reflection cũ)",
    )
    today: date | None = Field(
        default=None, description="Ngày hiện tại phía user (mặc định hôm nay của server)"
    )

    @field_validator("month")
    @classmethod
    def _first_day(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("month phải là ngày 1 của tháng")
        return value


class WeeklyReviewGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_start: date = Field(description="Thứ Hai đầu tuần")
    regenerate: bool = Field(
        default=False,
        description="true: tạo lại narrative/metrics cho review đã có (giữ reflection cũ)",
    )
    today: date | None = Field(
        default=None, description="Ngày hiện tại phía user (mặc định hôm nay của server)"
    )

    @field_validator("week_start")
    @classmethod
    def _monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start phải là Thứ Hai")
        return value


class ReflectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=MAX_REFLECTION_LENGTH)
    ] = ""
    flagged_transaction_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=MAX_FLAGGED_TRANSACTIONS,
        description="Khoản chi thuộc kỳ của review (tuần: “không đáng tiền”; tháng: khoản user "
        "muốn nhìn lại)",
    )


class PendingWeeklyReviewRead(BaseModel):
    has_pending: bool = Field(
        description="true khi hôm nay là Thứ Hai, tuần trước có giao dịch và review tuần trước "
        "chưa completed"
    )
    week_start: date = Field(description="Thứ Hai của tuần trước")
    review_id: uuid.UUID | None
    review_status: ReviewStatus | None
