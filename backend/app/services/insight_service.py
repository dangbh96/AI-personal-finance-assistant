"""Số liệu cho Financial Coach (Phase 10) — deterministic, chỉ đọc, không gọi AI (ADR-005).

Mỗi hàm là nguồn dữ liệu của một tool read-only trong `agents/tools/finance_tools`:

- `get_spending_summary`: tổng thu / chi trong khoảng ngày, theo danh mục hoặc spending_type.
- `get_category_trend`: chi theo danh mục qua N tháng (mặc định kết thúc ở tháng đã trọn gần nhất),
  chênh lệch so với tháng trước, trung bình, độ lệch chuẩn population (đồng) và hạng biến động.
- `get_budget_status`: Budget vs Actual (Phase 5) + vùng (Phase 9) dạng rút gọn.
- `get_budget_advice`: tư vấn điều chỉnh đã có (Phase 8) — không tạo mới (tạo mới là thao tác ghi).
- `get_recent_reviews`: review tuần / tháng đã tạo (Phase 6, 7).

Mọi số (tổng, %, biến động) tính ở đây; model chỉ trích lại.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import Category
from app.repositories import transaction_repository
from app.schemas.coach import (
    MAX_RANGE_DAYS,
    BudgetAdviceBrief,
    BudgetAdviceInput,
    BudgetAdviceOutput,
    BudgetLineBrief,
    BudgetStatusInput,
    BudgetStatusOutput,
    CategoryTrendInput,
    CategoryTrendItem,
    CategoryTrendOutput,
    RecentReviewsInput,
    RecentReviewsOutput,
    ReviewBrief,
    ReviewCategoryBrief,
    SpendingSummaryInput,
    SpendingSummaryItem,
    SpendingSummaryOutput,
)
from app.schemas.review import ReviewMetrics
from app.services import (
    advice_narrative,
    analytics_service,
    budget_advice_service,
    budget_service,
    category_service,
    review_service,
    zone_service,
)
from app.services.analytics_service import to_float
from app.services.money import add_months, month_range, round_vnd

SPENDING_TYPE_LABELS = {
    "essential": "Thiết yếu",
    "non_essential": "Không thiết yếu",
    "irregular": "Bất thường",
}


def share_pct(part: int, whole: int) -> float | None:
    """`part / whole × 100`, 1 chữ số (nửa ra xa 0); `None` nếu whole = 0."""
    if whole <= 0:
        return None
    return to_float(Fraction(part * 100, whole), 1)


def change_pct(current: int, previous: int) -> int | None:
    """% thay đổi nguyên (nửa ra xa 0) như review Phase 6; `None` nếu previous = 0."""
    if previous == 0:
        return None
    return round_vnd(Fraction((current - previous) * 100, previous))


def _categories(db: Session) -> dict:
    return {c.id: c for c in category_service.list_categories(db, include_archived=True)}


# ---------- get_spending_summary ----------


def _check_range(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise DomainError("from_date phải trước hoặc bằng to_date", "invalid_date_range")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise DomainError(f"Khoảng ngày tối đa {MAX_RANGE_DAYS} ngày", "date_range_too_long")


def get_spending_summary(db: Session, data: SpendingSummaryInput) -> SpendingSummaryOutput:
    _check_range(data.from_date, data.to_date)
    rows = transaction_repository.expense_totals_by_category_and_spending_type(
        db, data.from_date, data.to_date
    )
    by_direction = transaction_repository.totals_by_direction(db, data.from_date, data.to_date)
    income = by_direction.get("income", 0)
    expense = by_direction.get("expense", 0)

    totals: dict[object, list[int]] = defaultdict(lambda: [0, 0])
    for category_id, spending_type, total, count in rows:
        key = category_id if data.group_by == "category" else spending_type
        totals[key][0] += total
        totals[key][1] += count

    categories = _categories(db) if data.group_by == "category" else {}
    items = []
    for key, (total, count) in totals.items():
        category: Category | None = categories.get(key)
        items.append(
            SpendingSummaryItem(
                category_slug=category.slug if category else None,
                category_name=category.name if category else None,
                spending_type=None if data.group_by == "category" else key,  # type: ignore[arg-type]
                total=total,
                transaction_count=count,
                share_pct=share_pct(total, expense),
            )
        )
    items.sort(key=lambda i: (-i.total, i.category_name or i.spending_type or ""))
    return SpendingSummaryOutput(
        from_date=data.from_date,
        to_date=data.to_date,
        group_by=data.group_by,
        income_total=income,
        expense_total=expense,
        net=income - expense,
        items=items,
    )


# ---------- get_category_trend ----------


@dataclass
class CategorySeries:
    """Chi tiêu một danh mục theo từng tháng của chuỗi (cùng thứ tự với `months`)."""

    slug: str
    name: str
    totals: list[int]
    irregular_total: int = 0
    transaction_count: int = 0


def month_key(month: date) -> str:
    return f"{month:%Y-%m}"


def trend_months(end_month: date, months: int) -> list[date]:
    """`months` tháng (ngày 1) kết thúc ở tháng chứa `end_month`, cũ nhất trước."""
    end = month_range(end_month)[0]
    return [add_months(end, i - months + 1) for i in range(months)]


def build_trend_items(
    months: Sequence[date], series: Iterable[CategorySeries]
) -> list[CategoryTrendItem]:
    """Hàm thuần: thống kê + hạng biến động (độ lệch chuẩn lớn nhất = 1; hoà → tháng cuối lớn
    hơn, rồi slug). Kết quả sắp theo `latest_total` giảm dần."""
    stats = []
    for s in series:
        mean, std = zone_service.history_stats(s.totals)
        stats.append((s, round_vnd(mean), round_vnd(std)))
    ranked = sorted(stats, key=lambda x: (-x[2], -x[0].totals[-1], x[0].slug))
    rank = {x[0].slug: i + 1 for i, x in enumerate(ranked)}

    items = []
    for s, average, volatility in stats:
        latest = s.totals[-1]
        previous = s.totals[-2] if len(s.totals) > 1 else 0
        items.append(
            CategoryTrendItem(
                category_slug=s.slug,
                category_name=s.name,
                totals_by_month={
                    month_key(m): total for m, total in zip(months, s.totals, strict=True)
                },
                latest_total=latest,
                previous_total=previous,
                delta_vs_previous=latest - previous,
                delta_vs_previous_pct=change_pct(latest, previous),
                average=average,
                volatility=volatility,
                volatility_rank=rank[s.slug],
                irregular_total=s.irregular_total,
                transaction_count=s.transaction_count,
            )
        )
    items.sort(key=lambda i: (-i.latest_total, i.volatility_rank))
    return items


def default_trend_end(today: date) -> date:
    """Tháng đã trọn gần nhất (tháng trước tháng chứa `today`)."""
    return add_months(month_range(today)[0], -1)


def get_category_trend(db: Session, data: CategoryTrendInput, today: date) -> CategoryTrendOutput:
    end = month_range(data.end_month or default_trend_end(today))[0]
    if end > month_range(today)[0]:
        raise DomainError("end_month không được ở tương lai", "month_in_future")
    months = trend_months(end, data.months)
    categories = _categories(db)
    wanted = None
    if data.category_slug:
        category = next((c for c in categories.values() if c.slug == data.category_slug), None)
        if category is None or category.kind != "expense":
            raise NotFoundError(
                f"Không có danh mục chi tiêu '{data.category_slug}'", "category_not_found"
            )
        wanted = category.id

    series: dict[object, CategorySeries] = {}
    for index, month in enumerate(months):
        rows = transaction_repository.expense_totals_by_category_and_spending_type(
            db, *month_range(month)
        )
        for category_id, spending_type, total, count in rows:
            if wanted is not None and category_id != wanted:
                continue
            category = categories[category_id]
            s = series.setdefault(
                category_id, CategorySeries(category.slug, category.name, [0] * len(months))
            )
            s.totals[index] += total
            s.transaction_count += count
            if spending_type == "irregular":
                s.irregular_total += total
    if wanted is not None and wanted not in series:
        category = categories[wanted]
        series[wanted] = CategorySeries(category.slug, category.name, [0] * len(months))

    items = build_trend_items(months, series.values())
    most_volatile = next((i.category_name for i in items if i.volatility_rank == 1), None)
    return CategoryTrendOutput(
        months=[month_key(m) for m in months],
        from_date=months[0],
        to_date=month_range(months[-1])[1],
        items=items,
        most_volatile=most_volatile,
    )


# ---------- get_budget_status ----------


def get_budget_status(db: Session, data: BudgetStatusInput, today: date) -> BudgetStatusOutput:
    month = month_range(data.month or today)[0]
    try:
        budget = analytics_service.tracked_budget(db, month)
    except NotFoundError as exc:
        return BudgetStatusOutput(
            available=False,
            month=month,
            reason=exc.detail,
            budget_status=None,
            elapsed_days=None,
            days_in_month=None,
            month_progress_pct=None,
            income_actual=None,
            expense_planned=None,
            expense_actual=None,
            expense_variance=None,
            unbudgeted_actual=None,
            over_budget_count=None,
            lines=[],
        )
    status = analytics_service.get_budget_status(db, budget, today)
    lines = []
    for a in status.allocations:
        top = a.top_contributor
        lines.append(
            BudgetLineBrief(
                label=budget_service.allocation_label(
                    a.category.name if a.category else None, a.jar_name
                ),
                group=a.group,
                category_slug=a.category.slug if a.category else None,
                planned=a.planned,
                actual=a.actual,
                variance=a.variance,
                used_percent=a.used_percent,
                status=a.status,
                pace_status=a.pace_status,
                zone=a.zone.zone if a.zone else None,
                comfort_high=a.zone.comfort_high if a.zone else None,
                warning_threshold=a.zone.warning_threshold if a.zone else None,
                top_contributor_note=top.note if top else None,
                top_contributor_amount=top.amount if top else None,
                top_contributor_share_pct=to_float(Fraction(str(top.share)) * 100, 1)
                if top
                else None,
            )
        )
    progress, totals = status.progress, status.totals
    return BudgetStatusOutput(
        available=True,
        month=month,
        reason=None,
        budget_status=status.status,
        elapsed_days=progress.elapsed_days,
        days_in_month=progress.days_in_month,
        month_progress_pct=share_pct(progress.elapsed_days, progress.days_in_month),
        income_actual=totals.income_actual,
        expense_planned=totals.expense_planned,
        expense_actual=totals.expense_actual,
        expense_variance=totals.expense_variance,
        unbudgeted_actual=totals.unbudgeted_actual,
        over_budget_count=totals.over_budget_count,
        lines=lines,
    )


# ---------- get_budget_advice ----------


def get_budget_advice(db: Session, data: BudgetAdviceInput) -> BudgetAdviceOutput:
    advice = budget_advice_service.list_advice(db, month=data.month, status=data.status)
    month = month_range(data.month)[0] if data.month else (advice[0].month if advice else None)
    advice = [a for a in advice if a.month == month]
    if not advice:
        return BudgetAdviceOutput(
            month=month,
            items=[],
            note="Chưa có tư vấn điều chỉnh ngân sách phù hợp — user có thể tạo ở /budget/advice.",
        )
    items = []
    for a in advice:
        read = budget_advice_service.to_read(a)
        e = read.evidence
        items.append(
            BudgetAdviceBrief(
                label=read.allocation_label,
                month=read.month,
                verdict=read.verdict,
                verdict_label=advice_narrative.VERDICT_LABELS[read.verdict],
                status=read.status,
                planned_amount=e.planned_amount,
                actual_amount=e.actual_amount,
                variance=e.variance,
                proposed_planned_amount=e.proposed_planned_amount,
                explanation=read.explanation,
            )
        )
    return BudgetAdviceOutput(month=month, items=items, note=None)


# ---------- get_recent_reviews ----------


def _review_brief(
    kind: str, start: date, end: date, metrics: Mapping, narrative: Mapping
) -> ReviewBrief:
    m = ReviewMetrics.model_validate(metrics)
    return ReviewBrief(
        kind=kind,  # type: ignore[arg-type]
        period_start=start,
        period_end=end,
        complete=m.complete,
        income=m.income,
        expense=m.expense,
        net=m.net,
        expense_change=m.expense_change,
        expense_change_pct=m.expense_change_pct,
        top_categories=[
            ReviewCategoryBrief(category_name=c.name, amount=c.amount)
            for c in m.highlights.top_categories
        ],
        observation=str(narrative.get("observation", "")),
    )


def get_recent_reviews(db: Session, data: RecentReviewsInput) -> RecentReviewsOutput:
    items: list[ReviewBrief] = []
    if data.kind in ("monthly", "all"):
        for r in review_service.list_monthly(db)[: data.limit]:
            items.append(
                _review_brief(
                    "monthly", r.month, review_service.month_end(r.month), r.metrics, r.narrative
                )
            )
    if data.kind in ("weekly", "all"):
        for r in review_service.list_weekly(db)[: data.limit]:
            items.append(
                _review_brief(
                    "weekly",
                    r.week_start,
                    review_service.week_end(r.week_start),
                    r.metrics,
                    r.narrative,
                )
            )
    items.sort(key=lambda i: (i.period_end, i.kind == "monthly"), reverse=True)
    note = None if items else "Chưa có review nào — user có thể tạo ở /reviews/weekly."
    return RecentReviewsOutput(items=items, note=note)
