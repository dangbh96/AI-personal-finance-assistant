"""Schema Financial Coach (Phase 10): input / output của tool read-only, hội thoại, tool trace.

Mọi số trong output tool do `services/insight_service` tính (deterministic, ADR-005). Tiền là số
nguyên đồng (ADR-007); `*_pct` là phần trăm 1 chữ số (để câu trả lời trích được mà không phải
tự tính).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import (
    AdviceStatus,
    AdviceVerdict,
    AllocationGroup,
    BudgetStatus,
    ChatRole,
    CoachGuardStatus,
    SpendingType,
    ZoneStatus,
)
from app.schemas.analytics import AllocationTrackingStatus, PaceStatus

MAX_MESSAGE_LENGTH = 2000
MAX_TITLE_LENGTH = 120
MAX_RANGE_DAYS = 366

ReviewKindFilter = Literal["weekly", "monthly", "all"]
SummaryGroupBy = Literal["category", "spending_type"]

# ---------- tool: get_spending_summary ----------


class SpendingSummaryInput(BaseModel):
    """Tổng thu / chi trong khoảng ngày, chia theo danh mục hoặc loại chi tiêu."""

    from_date: date = Field(description="Ngày bắt đầu (YYYY-MM-DD), bao gồm")
    to_date: date = Field(description="Ngày kết thúc (YYYY-MM-DD), bao gồm; tối đa 366 ngày")
    group_by: SummaryGroupBy = Field(
        default="category",
        description="category: theo danh mục · spending_type: Thiết yếu / Không thiết yếu / "
        "Bất thường",
    )


class SpendingSummaryItem(BaseModel):
    category_slug: str | None
    category_name: str | None
    spending_type: SpendingType | None
    total: int
    transaction_count: int
    share_pct: float | None = Field(description="total / expense_total × 100 (1 chữ số)")


class SpendingSummaryOutput(BaseModel):
    from_date: date
    to_date: date
    group_by: SummaryGroupBy
    income_total: int
    expense_total: int
    net: int = Field(description="income_total - expense_total")
    items: list[SpendingSummaryItem] = Field(description="Chi nhiều nhất trước")


# ---------- tool: get_category_trend ----------


class CategoryTrendInput(BaseModel):
    """Chi tiêu theo danh mục qua nhiều tháng + mức biến động."""

    months: int = Field(default=3, ge=2, le=12, description="Số tháng (2–12)")
    category_slug: str | None = Field(
        default=None, description="Chỉ một danh mục (slug, vd food); null = mọi danh mục có chi"
    )
    end_month: date | None = Field(
        default=None,
        description="Một ngày trong tháng cuối của chuỗi; mặc định tháng trước tháng hiện tại "
        "(tháng đã trọn)",
    )


class CategoryTrendItem(BaseModel):
    category_slug: str
    category_name: str
    totals_by_month: dict[str, int] = Field(description="Khoá YYYY-MM, cũ nhất trước")
    latest_total: int = Field(description="Tổng chi tháng cuối")
    previous_total: int = Field(description="Tổng chi tháng liền trước tháng cuối")
    delta_vs_previous: int = Field(description="latest_total - previous_total")
    delta_vs_previous_pct: int | None = Field(description="null nếu previous_total = 0")
    average: int = Field(description="Trung bình các tháng (làm tròn tới đồng)")
    volatility: int = Field(description="Độ lệch chuẩn (population) các tháng, đồng")
    volatility_rank: int = Field(description="1 = biến động lớn nhất")
    irregular_total: int = Field(description="Tổng giao dịch Bất thường trong cả chuỗi tháng")
    transaction_count: int


class CategoryTrendOutput(BaseModel):
    months: list[str] = Field(description="Các tháng YYYY-MM, cũ nhất trước")
    from_date: date
    to_date: date
    items: list[CategoryTrendItem] = Field(description="latest_total lớn nhất trước")
    most_volatile: str | None = Field(description="Tên danh mục biến động lớn nhất")


# ---------- tool: get_budget_status ----------


class BudgetStatusInput(BaseModel):
    """Ngân sách vs thực chi của một tháng (budget active / closed)."""

    month: date | None = Field(
        default=None, description="Một ngày trong tháng (YYYY-MM-DD); mặc định tháng hiện tại"
    )


class BudgetLineBrief(BaseModel):
    label: str
    group: AllocationGroup
    category_slug: str | None
    planned: int
    actual: int
    variance: int = Field(description="actual - planned (dương = vượt)")
    used_percent: float | None
    status: AllocationTrackingStatus
    pace_status: PaceStatus | None
    zone: ZoneStatus | None = Field(description="null = chưa đặt vùng (không suy ra 🟢)")
    comfort_high: int | None
    warning_threshold: int | None
    top_contributor_note: str | None
    top_contributor_amount: int | None
    top_contributor_share_pct: float | None


class BudgetStatusOutput(BaseModel):
    available: bool = Field(description="false nếu tháng chưa có ngân sách active / closed")
    month: date
    reason: str | None
    budget_status: BudgetStatus | None
    elapsed_days: int | None
    days_in_month: int | None
    month_progress_pct: float | None
    income_actual: int | None
    expense_planned: int | None
    expense_actual: int | None
    expense_variance: int | None
    unbudgeted_actual: int | None
    over_budget_count: int | None
    lines: list[BudgetLineBrief]


# ---------- tool: get_budget_advice ----------


class BudgetAdviceInput(BaseModel):
    """Tư vấn điều chỉnh ngân sách đã tạo (không tạo mới)."""

    month: date | None = Field(
        default=None, description="Một ngày trong tháng; mặc định tháng gần nhất có tư vấn"
    )
    status: AdviceStatus | None = Field(default=None, description="open | accepted | dismissed")


class BudgetAdviceBrief(BaseModel):
    label: str
    month: date
    verdict: AdviceVerdict
    verdict_label: str
    status: AdviceStatus
    planned_amount: int
    actual_amount: int
    variance: int
    proposed_planned_amount: int | None
    explanation: str


class BudgetAdviceOutput(BaseModel):
    month: date | None
    items: list[BudgetAdviceBrief]
    note: str | None


# ---------- tool: get_recent_reviews ----------


class RecentReviewsInput(BaseModel):
    """Review tuần / tháng gần nhất đã tạo."""

    kind: ReviewKindFilter = Field(default="all", description="weekly | monthly | all")
    limit: int = Field(default=3, ge=1, le=6, description="Số review mỗi loại")


class ReviewCategoryBrief(BaseModel):
    category_name: str
    amount: int


class ReviewBrief(BaseModel):
    kind: Literal["weekly", "monthly"]
    period_start: date
    period_end: date
    complete: bool
    income: int
    expense: int
    net: int
    expense_change: int
    expense_change_pct: int | None
    top_categories: list[ReviewCategoryBrief]
    observation: str


class RecentReviewsOutput(BaseModel):
    items: list[ReviewBrief] = Field(description="Mới nhất trước")
    note: str | None


# ---------- tool: get_goals (Phase 11) ----------


class GoalsInput(BaseModel):
    """Các mục tiêu tiết kiệm đang thực hiện (không tham số)."""


class GoalToolItem(BaseModel):
    goal_id: uuid.UUID
    name: str
    target_amount: int
    current_amount: int
    remaining_amount: int
    progress_pct: float = Field(description="current / target × 100 (1 chữ số)")
    deadline: date
    months_remaining: int = Field(description="Tính cả tháng hiện tại; 0 = đã quá hạn")
    suggested_monthly_saving: int = Field(description="Số nên để dành mỗi tháng")
    on_track: bool
    overdue: bool
    priority: int = Field(description="1 = ưu tiên cao nhất")


class GetGoalsOutput(BaseModel):
    active_goals: list[GoalToolItem] = Field(description="Theo priority")
    total_suggested_monthly_saving: int
    paused_count: int
    achieved_count: int
    note: str | None


# ---------- tool trace / evidence ----------


class ToolTraceItem(BaseModel):
    name: str
    args: dict[str, Any]
    result_summary: str
    result_count: int = Field(description="Số dòng kết quả (danh mục, dòng ngân sách…)")
    evidence_refs: list[str] = Field(description="Mã dòng evidence (E1, E2…) lấy từ tool này")
    latency_ms: int
    error: str | None = None


class EvidenceItem(BaseModel):
    ref: str = Field(description="E1, E2…")
    tool: str
    label: str = Field(description="Danh mục / dòng ngân sách / kỳ review")
    period: str = Field(description="Vd 09/2026 hoặc 01/09–30/09/2026")
    metric: str = Field(description="Vd Chi tiêu, Ngân sách, Chênh lệch")
    amount: int


class ChatMessageMetadata(BaseModel):
    model: str | None
    prompt_version: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_vnd: int | None
    llm_calls: int
    tool_rounds: int
    latency_ms: int
    guard_status: CoachGuardStatus
    guard_problems: list[str] = Field(default_factory=list)


class CoachAnswer(BaseModel):
    """Kết quả một lượt `coach_graph` (chưa lưu)."""

    content: str
    tool_trace: list[ToolTraceItem]
    evidence: list[EvidenceItem]
    metadata: ChatMessageMetadata


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


# ---------- API ----------

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH)
]
MessageContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH)
]


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = Field(default=None, description="Bỏ trống → đặt theo câu hỏi đầu tiên")


class ChatSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title


class ChatSessionRead(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatSessionSummary(ChatSessionRead):
    last_message_preview: str | None
    message_count: int


class ChatSessionList(BaseModel):
    items: list[ChatSessionSummary] = Field(description="Cập nhật gần nhất trước")


class ChatMessageRead(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: ChatRole
    content: str
    tool_calls: list[ToolTraceItem] | None
    evidence: list[EvidenceItem] | None
    metadata: ChatMessageMetadata | None
    created_at: datetime


class ChatSessionDetail(ChatSessionRead):
    messages: list[ChatMessageRead] = Field(description="Cũ nhất trước")


class CoachMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: MessageContent
    today: date | None = Field(
        default=None, description="Hôm nay phía user (mặc định của server) — dùng cho demo/test"
    )


class CoachMessageResponse(BaseModel):
    session: ChatSessionRead
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead
    tool_trace: list[ToolTraceItem]
    evidence: list[EvidenceItem]
    guard_status: CoachGuardStatus
