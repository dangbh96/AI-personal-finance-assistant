"""Schema Weekly review (Phase 6, dùng lại cho Monthly review ở Phase 7).

Tiền là số nguyên đồng (ADR-007); `*_change_pct` là phần trăm nguyên (làm tròn half-up), `null`
khi kỳ trước bằng 0. Mọi số trong narrative phải lấy từ `ReviewMetrics` (ADR-005).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import ReviewPeriod, ReviewStatus, SpendingType

TimeBucket = Literal["morning", "noon", "evening"]
NarrativeTone = Literal["neutral", "supportive"]

MAX_REFLECTION_LENGTH = 2000
MAX_FLAGGED_TRANSACTIONS = 50


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
    """Lưu ở `weekly_reviews.narrative`."""

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
        description='Giao dịch chi trong tuần user thấy "không đáng tiền"',
    )


class PendingWeeklyReviewRead(BaseModel):
    has_pending: bool = Field(
        description="true khi hôm nay là Thứ Hai, tuần trước có giao dịch và review tuần trước "
        "chưa completed"
    )
    week_start: date = Field(description="Thứ Hai của tuần trước")
    review_id: uuid.UUID | None
    review_status: ReviewStatus | None
