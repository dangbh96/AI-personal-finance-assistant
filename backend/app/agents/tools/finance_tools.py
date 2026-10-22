"""Tool read-only của Financial Coach — chỉ gọi services (`insight_service`, `goal_service`,
`search_service`, `knowledge_service` đọc; không repository, không ghi DB). Output là JSON của
schema trong `schemas/coach.py`; recorder giữ bản Pydantic để dựng evidence / citations và tập số
được phép cho `response_guard`. `search_transactions` / `search_knowledge` dùng `ctx.embedder` (do
`coach_graph` gắn) để embed câu tìm.
"""

from datetime import date

from langchain_core.tools import BaseTool, tool

from app.agents.tools.registry import CoachToolContext, CoachToolRegistry
from app.core.errors import DomainError
from app.schemas.coach import (
    BudgetAdviceInput,
    BudgetStatusInput,
    CategoryTrendInput,
    GoalsInput,
    RecentReviewsInput,
    SearchKnowledgeInput,
    SearchTransactionsInput,
    SimulateInput,
    SpendingSummaryInput,
)
from app.services import (
    goal_service,
    insight_service,
    knowledge_service,
    search_service,
    simulator_service,
)


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


def goals_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "get_goals",
        args_schema=GoalsInput,
        description="Các mục tiêu tiết kiệm đang thực hiện (theo ưu tiên): số tiền mục tiêu, đã "
        "có, còn thiếu, % tiến độ, hạn, số tháng còn lại, số nên để dành mỗi tháng, đúng tiến độ "
        "hay đã quá hạn; tổng số nên để dành mỗi tháng cho mọi mục tiêu. Chỉ đọc.",
    )
    def get_goals() -> str:
        return ctx.recorder.store(goal_service.get_goals_overview(ctx.db, ctx.today))

    return get_goals


def search_transactions_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "search_transactions",
        args_schema=SearchTransactionsInput,
        description="Tìm giao dịch theo ý nghĩa tiếng Việt (vd 'ăn ngoài' tìm được 'nhà hàng', "
        "'bún chả'; 'đi lại' tìm được 'grab', 'xăng'), có thể lọc khoảng ngày. Trả danh sách "
        "giao dịch (ngày, ghi chú, danh mục, số tiền) xếp theo độ liên quan + tổng thu / chi của "
        "các dòng trả về. Dùng khi câu hỏi nhắc tới một loại chi tiêu cụ thể không trùng tên "
        "danh mục, hoặc cần liệt kê giao dịch. Chỉ đọc.",
    )
    def search_transactions(
        query: str,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 10,
    ) -> str:
        if ctx.embedder is None:
            raise DomainError("Tìm kiếm ngữ nghĩa chưa sẵn sàng", "search_unavailable")
        data = SearchTransactionsInput(
            query=query, from_date=from_date, to_date=to_date, limit=limit
        )
        return ctx.recorder.store(search_service.search_for_coach(ctx.db, data, ctx.embedder))

    return search_transactions


def search_knowledge_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "search_knowledge",
        args_schema=SearchKnowledgeInput,
        description="Tra thư viện kiến thức tài chính cá nhân của app (50/30/20, phương pháp hũ / "
        "phong bì, Pay Yourself First, quỹ khẩn cấp, sinking fund, nợ cơ bản). Trả các đoạn "
        "liên quan kèm `citation` để ghi mục Nguồn. Dùng cho câu hỏi khái niệm / phương pháp; "
        "không chứa số liệu của người dùng. Chỉ đọc.",
    )
    def search_knowledge(query: str, limit: int = 4) -> str:
        if ctx.embedder is None:
            raise DomainError("Thư viện kiến thức chưa sẵn sàng", "knowledge_unavailable")
        data = SearchKnowledgeInput(query=query, limit=limit)
        return ctx.recorder.store(knowledge_service.search_for_coach(ctx.db, data, ctx.embedder))

    return search_knowledge


def simulate_tool(ctx: CoachToolContext) -> BaseTool:
    @tool(
        "simulate",
        args_schema=SimulateInput,
        description="Mô phỏng what-if (KHÔNG ghi dữ liệu): giảm chi một danh mục theo %, tăng / "
        "giảm thu nhập mỗi tháng, hoặc thêm một khoản chi định kỳ mỗi tháng — trên mức trung "
        "bình các tháng gần nhất. Trả tiết kiệm / tháng trước / sau / chênh lệch và số ngày đạt "
        "từng mục tiêu trước / sau (sớm hơn bao nhiêu ngày). Dùng cho câu 'Nếu … thì sao?'.",
    )
    def simulate(
        reduce_category_slug: str | None = None,
        reduce_percent: int | None = None,
        income_delta: int | None = None,
        add_expense_name: str | None = None,
        add_expense_amount: int | None = None,
        add_expense_category_slug: str | None = None,
        months: int = 3,
    ) -> str:
        data = SimulateInput(
            reduce_category_slug=reduce_category_slug,
            reduce_percent=reduce_percent,
            income_delta=income_delta,
            add_expense_name=add_expense_name,
            add_expense_amount=add_expense_amount,
            add_expense_category_slug=add_expense_category_slug,
            months=months,
        )
        return ctx.recorder.store(simulator_service.simulate_for_coach(ctx.db, data, ctx.today))

    return simulate


def default_registry() -> CoachToolRegistry:
    registry = CoachToolRegistry()
    registry.register("get_spending_summary", spending_summary_tool)
    registry.register("get_budget_status", budget_status_tool)
    registry.register("get_category_trend", category_trend_tool)
    registry.register("get_budget_advice", budget_advice_tool)
    registry.register("get_recent_reviews", recent_reviews_tool)
    registry.register("get_goals", goals_tool)
    registry.register("search_transactions", search_transactions_tool)
    registry.register("search_knowledge", search_knowledge_tool)
    registry.register("simulate", simulate_tool)
    return registry
