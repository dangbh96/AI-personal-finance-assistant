"""5 tool read-only của Financial Coach — chỉ gọi `services/insight_service` (không repository,
không ghi DB). Output là JSON của schema trong `schemas/coach.py`; recorder giữ bản Pydantic để
dựng evidence và tập số được phép cho `response_guard`.
"""

from datetime import date

from langchain_core.tools import BaseTool, tool

from app.agents.tools.registry import CoachToolContext, CoachToolRegistry
from app.schemas.coach import (
    BudgetAdviceInput,
    BudgetStatusInput,
    CategoryTrendInput,
    RecentReviewsInput,
    SpendingSummaryInput,
)
from app.services import insight_service


def spending_summary_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_spending_summary",
        args_schema=SpendingSummaryInput,
        description="Tổng thu, tổng chi và chi tiêu theo danh mục (group_by=category) hoặc theo "
        "loại Thiết yếu / Không thiết yếu / Bất thường (group_by=spending_type) trong một "
        "khoảng ngày (tối đa 366 ngày). Có số giao dịch và tỉ trọng % trong tổng chi.",
    )
    def get_spending_summary(from_date: date, to_date: date, group_by: str = "category") -> str:
        data = SpendingSummaryInput(from_date=from_date, to_date=to_date, group_by=group_by)  # type: ignore[arg-type]
        return ctx.recorder.store(insight_service.get_spending_summary(ctx.db, data))

    return get_spending_summary


def category_trend_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_category_trend",
        args_schema=CategoryTrendInput,
        description="Chi tiêu từng danh mục qua N tháng (mặc định 3 tháng, kết thúc ở tháng đã "
        "trọn gần nhất): tổng từng tháng, tháng cuối, chênh lệch so với tháng trước, trung bình, "
        "độ biến động và hạng biến động (1 = biến động lớn nhất), tổng khoản bất thường. Dùng "
        "cho câu hỏi 'nên giảm khoản nào', 'khoản nào tăng'.",
    )
    def get_category_trend(
        months: int = 3, category_slug: str | None = None, end_month: date | None = None
    ) -> str:
        data = CategoryTrendInput(months=months, category_slug=category_slug, end_month=end_month)
        return ctx.recorder.store(insight_service.get_category_trend(ctx.db, data, ctx.today))

    return get_category_trend


def budget_status_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_budget_status",
        args_schema=BudgetStatusInput,
        description="Ngân sách so với thực chi của một tháng (mặc định tháng hiện tại): từng dòng "
        "planned / actual / variance (dương = vượt), % đã dùng, trạng thái, vùng 🟢🟡🔴 (null = "
        "chưa đặt vùng), giao dịch lớn nhất khi vượt; tổng chi, chi ngoài ngân sách, tiến độ "
        "tháng. available=false nếu tháng chưa có ngân sách đang theo dõi.",
    )
    def get_budget_status(month: date | None = None) -> str:
        data = BudgetStatusInput(month=month)
        return ctx.recorder.store(insight_service.get_budget_status(ctx.db, data, ctx.today))

    return get_budget_status


def budget_advice_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_budget_advice",
        args_schema=BudgetAdviceInput,
        description="Các tư vấn điều chỉnh ngân sách đã tạo (không tạo mới): kết luận (ngân sách "
        "đặt thấp / nên xem lại nhịp chi / khoản một lần / trong kế hoạch), planned, actual, "
        "ngân sách đề xuất, trạng thái và lời giải thích. Mặc định tháng gần nhất có tư vấn.",
    )
    def get_budget_advice(month: date | None = None, status: str | None = None) -> str:
        data = BudgetAdviceInput(month=month, status=status)  # type: ignore[arg-type]
        return ctx.recorder.store(insight_service.get_budget_advice(ctx.db, data))

    return get_budget_advice


def recent_reviews_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_recent_reviews",
        args_schema=RecentReviewsInput,
        description="Các review tuần / tháng gần nhất đã tạo: thu, chi, thay đổi so với kỳ "
        "trước, danh mục chi nhiều nhất và phần quan sát.",
    )
    def get_recent_reviews(kind: str = "all", limit: int = 3) -> str:
        data = RecentReviewsInput(kind=kind, limit=limit)  # type: ignore[arg-type]
        return ctx.recorder.store(insight_service.get_recent_reviews(ctx.db, data))

    return get_recent_reviews


def default_registry() -> CoachToolRegistry:
    registry = CoachToolRegistry()
    registry.register("get_spending_summary", spending_summary_tool)
    registry.register("get_budget_status", budget_status_tool)
    registry.register("get_category_trend", category_trend_tool)
    registry.register("get_budget_advice", budget_advice_tool)
    registry.register("get_recent_reviews", recent_reviews_tool)
    return registry
