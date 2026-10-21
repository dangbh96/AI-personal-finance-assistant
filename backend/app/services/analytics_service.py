"""Budget vs Actual (Phase 5) — deterministic, không gọi AI (ADR-005). Tiền là số nguyên đồng.

- Actual của một dòng phân bổ = tổng giao dịch chi trong tháng khớp
  `budget_service.allocation_scope` (danh mục / hũ / spending_type). Nhóm `savings` không có
  actual (= 0) cho tới Phase 11.
- `variance = actual - planned`, `remaining = planned - actual`, `used_percent = actual / planned`.
- Pro-rata: `month_progress = ngày đã qua (tính cả hôm nay) / số ngày trong tháng`;
  `pace_status` so used % với % tháng đã qua, dung sai `PACE_TOLERANCE` (10 điểm %).
- Top contributor: dòng đang vượt mà giao dịch lớn nhất chiếm ≥ `TOP_CONTRIBUTOR_MIN_SHARE`
  (60%) phần vượt.
- Review (Phase 6, 7): đọc giao dịch kỳ này / kỳ trước cho `review_metrics`; kỳ tháng gom thêm
  budget vs actual (`summarize_budget`) và phản tư các review tuần trong tháng.
- Vùng linh hoạt (Phase 9): mỗi dòng (trừ savings) kèm `zone` từ `zone_service` (ngưỡng đã lưu +
  pro-rata); `get_budget_zones` thêm cách tính ngưỡng auto.
"""

import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Budget, BudgetAllocation, Category, Transaction
from app.models.enums import ReviewPeriod
from app.repositories import budget_repository, transaction_repository
from app.schemas.analytics import (
    AllocationScopeRead,
    AllocationStatusRead,
    AllocationTrackingStatus,
    BudgetStatusRead,
    BudgetStatusTotals,
    BudgetZoneList,
    BudgetZoneRead,
    MonthProgressRead,
    MonthSummaryRead,
    PaceStatus,
    TopContributorRead,
)
from app.schemas.category import CategoryBrief
from app.schemas.review import (
    BudgetLineSummary,
    MonthlyBudgetSummary,
    PeriodMetrics,
    ReviewMetrics,
    WeeklyReflectionDigest,
)
from app.services import budget_service, review_metrics, review_service, zone_service
from app.services.budget_service import AllocationScope
from app.services.money import elapsed_days, month_range, round_vnd
from app.services.review_metrics import TxRow

PACE_TOLERANCE = Fraction(10, 100)
TOP_CONTRIBUTOR_MIN_SHARE = Fraction(60, 100)
TRACKED_BUDGET_STATUSES = frozenset({"active", "closed"})

# (category_id, spending_type, tổng tiền, số giao dịch) — kết quả aggregate chi tiêu trong tháng.
ExpenseRow = tuple[uuid.UUID, str | None, int, int]


# ---------- tính toán thuần (không đụng DB) ----------


def to_float(value: Fraction, digits: int) -> float:
    """Làm tròn nửa ra xa 0 tới `digits` chữ số thập phân (tránh lỗi làm tròn của float)."""
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return float(exact.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class MonthProgress:
    today: date
    date_from: date
    date_to: date
    elapsed_days: int
    days_in_month: int

    @property
    def ratio(self) -> Fraction:
        return Fraction(self.elapsed_days, self.days_in_month)

    def to_read(self) -> MonthProgressRead:
        return MonthProgressRead(
            today=self.today,
            date_from=self.date_from,
            date_to=self.date_to,
            elapsed_days=self.elapsed_days,
            days_in_month=self.days_in_month,
            month_progress=to_float(self.ratio, 4),
        )


def month_progress(period_month: date, today: date) -> MonthProgress:
    """Tháng chưa tới → 0 ngày; tháng đã qua → đủ số ngày; đang chạy → `today.day` ngày."""
    start, end = month_range(period_month)
    return MonthProgress(today, start, end, elapsed_days(period_month, today), end.day)


def used_percent(actual: int, planned: int) -> float | None:
    """`actual / planned × 100`, 1 chữ số thập phân; `None` nếu planned = 0."""
    if planned <= 0:
        return None
    return to_float(Fraction(actual * 100, planned), 1)


def expected_to_date(planned: int, progress: Fraction) -> int:
    """Mức chi "đúng nhịp" tới hôm nay: `planned × progress`, làm tròn tới đồng."""
    return round_vnd(planned * progress)


def pace_status(actual: int, planned: int, progress: Fraction) -> PaceStatus | None:
    if planned <= 0:
        return None
    used = Fraction(actual, planned)
    if used - progress > PACE_TOLERANCE:
        return "ahead"
    if progress - used > PACE_TOLERANCE:
        return "under"
    return "on_track"


def tracking_status(
    group: str, actual: int, planned: int, pace: PaceStatus | None
) -> AllocationTrackingStatus:
    if group == "savings":
        return "not_tracked"
    if actual > planned:
        return "over_budget"
    if pace == "ahead":
        return "ahead_of_pace"
    return "on_track"


def top_contributor_share(amount: int, overspend: int) -> Fraction | None:
    """Tỉ lệ phần vượt do 1 giao dịch gây ra (tối đa 1) nếu ≥ 60%, ngược lại `None`.

    >>> top_contributor_share(900_000, 1_200_000)
    Fraction(3, 4)
    """
    if overspend <= 0 or amount <= 0:
        return None
    share = Fraction(amount, overspend)
    if share < TOP_CONTRIBUTOR_MIN_SHARE:
        return None
    return min(share, Fraction(1))


def scope_actual(scope: AllocationScope, rows: Iterable[ExpenseRow]) -> tuple[int, int]:
    """Cộng các nhóm `(category_id, spending_type)` khớp phạm vi → `(tổng tiền, số giao dịch)`."""
    total = count = 0
    for category_id, spending_type, amount, n in rows:
        if category_id in scope.category_ids or spending_type in scope.spending_types:
            total += amount
            count += n
    return total, count


@dataclass(frozen=True)
class AllocationMetrics:
    planned: int
    actual: int
    variance: int
    remaining: int
    used_percent: float | None
    expected_to_date: int
    pace_status: PaceStatus | None
    status: AllocationTrackingStatus

    @property
    def overspend(self) -> int:
        return max(0, self.variance)


def evaluate_allocation(
    group: str, planned: int, actual: int, progress: Fraction
) -> AllocationMetrics:
    pace = None if group == "savings" else pace_status(actual, planned, progress)
    return AllocationMetrics(
        planned=planned,
        actual=actual,
        variance=actual - planned,
        remaining=planned - actual,
        used_percent=used_percent(actual, planned),
        expected_to_date=expected_to_date(planned, progress),
        pace_status=pace,
        status=tracking_status(group, actual, planned, pace),
    )


# ---------- phạm vi dòng phân bổ ----------


def effective_scope(
    strategy: str,
    allocation: BudgetAllocation,
    jar_categories: Mapping[str, Iterable[uuid.UUID]],
) -> AllocationScope:
    """`allocation_scope` của Phase 4, riêng nhóm `savings` không khớp giao dịch chi nào."""
    scope = budget_service.allocation_scope(strategy, allocation, jar_categories)
    if allocation.group == "savings":
        return AllocationScope(scope.kind)
    return scope


@dataclass(frozen=True)
class _BudgetContext:
    budget: Budget
    jar_ids: dict[str, list[uuid.UUID]]
    categories: dict[uuid.UUID, Category]

    def scope(self, allocation: BudgetAllocation) -> AllocationScope:
        return effective_scope(self.budget.strategy, allocation, self.jar_ids)

    def scope_read(
        self, allocation: BudgetAllocation, scope: AllocationScope
    ) -> AllocationScopeRead:
        categories = [self.categories[cid] for cid in scope.category_ids if cid in self.categories]
        if allocation.category is not None and allocation.category_id in scope.category_ids:
            categories = [allocation.category]
        return AllocationScopeRead(
            kind=scope.kind,
            categories=[
                CategoryBrief.model_validate(c) for c in sorted(categories, key=lambda c: c.name)
            ],
            spending_types=sorted(scope.spending_types),  # type: ignore[arg-type]
        )


def _context(db: Session, budget: Budget) -> _BudgetContext:
    jar_categories = budget_service.load_jar_categories(db) if budget.strategy == "envelope" else {}
    return _BudgetContext(
        budget=budget,
        jar_ids={name: [c.id for c in cats] for name, cats in jar_categories.items()},
        categories={c.id: c for cats in jar_categories.values() for c in cats},
    )


def scope_resolver(db: Session, budget: Budget) -> Callable[[BudgetAllocation], AllocationScope]:
    """Hàm trả phạm vi giao dịch (`effective_scope`) của từng dòng thuộc `budget`."""
    return _context(db, budget).scope


def tracked_budget(db: Session, month: date) -> Budget:
    """Budget đang theo dõi của tháng (active / closed); chưa có / nháp → 404."""
    return _tracked_budget(db, month)


# ---------- trạng thái budget ----------


def _top_contributor(
    db: Session, scope: AllocationScope, progress: MonthProgress, overspend: int
) -> TopContributorRead | None:
    largest: Transaction | None = transaction_repository.largest_in_scope(
        db, progress.date_from, progress.date_to, scope.category_ids, scope.spending_types
    )
    if largest is None:
        return None
    share = top_contributor_share(largest.amount, overspend)
    if share is None:
        return None
    return TopContributorRead(
        transaction_id=largest.id,
        occurred_on=largest.occurred_on,
        note=largest.note,
        category=CategoryBrief.model_validate(largest.category),
        spending_type=largest.spending_type,  # type: ignore[arg-type]
        amount=largest.amount,
        overspend=overspend,
        share=to_float(share, 4),
    )


def _allocation_status(
    db: Session,
    ctx: _BudgetContext,
    allocation: BudgetAllocation,
    rows: list[ExpenseRow],
    progress: MonthProgress,
) -> AllocationStatusRead:
    scope = ctx.scope(allocation)
    actual, count = scope_actual(scope, rows)
    metrics = evaluate_allocation(
        allocation.group, allocation.planned_amount, actual, progress.ratio
    )
    top = (
        _top_contributor(db, scope, progress, metrics.overspend)
        if metrics.status == "over_budget"
        else None
    )
    return AllocationStatusRead(
        id=allocation.id,
        position=allocation.position,
        group=allocation.group,  # type: ignore[arg-type]
        category_id=allocation.category_id,
        category=CategoryBrief.model_validate(allocation.category) if allocation.category else None,
        jar_name=allocation.jar_name,
        scope=ctx.scope_read(allocation, scope),
        planned=metrics.planned,
        actual=metrics.actual,
        variance=metrics.variance,
        remaining=metrics.remaining,
        used_percent=metrics.used_percent,
        transaction_count=count,
        expected_to_date=metrics.expected_to_date,
        pace_status=metrics.pace_status,
        status=metrics.status,
        top_contributor=top,
        zone=zone_service.allocation_zone(
            allocation, metrics.actual, progress.elapsed_days, progress.days_in_month
        ),
    )


def _totals(
    budget: Budget,
    allocations: list[AllocationStatusRead],
    income_actual: int,
    expense_actual: int,
) -> BudgetStatusTotals:
    expense_planned = sum(a.planned for a in allocations if a.group != "savings")
    allocated_actual = sum(a.actual for a in allocations)
    return BudgetStatusTotals(
        income_expected=budget.expected_income,
        income_actual=income_actual,
        income_variance=income_actual - budget.expected_income,
        expense_planned=expense_planned,
        expense_actual=expense_actual,
        expense_variance=expense_actual - expense_planned,
        expense_used_percent=used_percent(expense_actual, expense_planned),
        allocated_actual=allocated_actual,
        unbudgeted_actual=expense_actual - allocated_actual,
        savings_planned=sum(a.planned for a in allocations if a.group == "savings"),
        net_actual=income_actual - expense_actual,
        over_budget_count=sum(1 for a in allocations if a.status == "over_budget"),
    )


def get_budget_status(db: Session, budget: Budget, today: date) -> BudgetStatusRead:
    """Planned vs actual của mọi dòng + tổng tháng. Dùng được cho budget ở mọi trạng thái."""
    progress = month_progress(budget.period_month, today)
    rows = transaction_repository.expense_totals_by_category_and_spending_type(
        db, progress.date_from, progress.date_to
    )
    by_direction = transaction_repository.totals_by_direction(
        db, progress.date_from, progress.date_to
    )
    ctx = _context(db, budget)
    allocations = [_allocation_status(db, ctx, a, rows, progress) for a in budget.allocations]
    return BudgetStatusRead(
        budget_id=budget.id,
        period_month=budget.period_month,
        strategy=budget.strategy,  # type: ignore[arg-type]
        status=budget.status,  # type: ignore[arg-type]
        progress=progress.to_read(),
        totals=_totals(
            budget, allocations, by_direction.get("income", 0), by_direction.get("expense", 0)
        ),
        allocations=allocations,
    )


def get_budget_status_by_id(db: Session, budget_id: uuid.UUID, today: date) -> BudgetStatusRead:
    return get_budget_status(db, budget_service.get_budget(db, budget_id), today)


# ---------- vùng linh hoạt (Phase 9) ----------


def get_budget_zones(db: Session, budget_id: uuid.UUID, today: date) -> BudgetZoneList:
    """Ngưỡng + zone + pro-rata của mọi dòng chi tiêu; dòng auto kèm cách tính (`auto`)."""
    budget = budget_service.get_budget(db, budget_id)
    status = get_budget_status(db, budget, today)
    rows = {a.id: a for a in budget.allocations}
    auto_rows = [a for a in budget.allocations if a.zone_mode == "auto"]
    histories = zone_service.load_histories(db, budget, auto_rows)
    items = []
    for line in status.allocations:
        if line.zone is None:
            continue
        allocation = rows[line.id]
        items.append(
            BudgetZoneRead(
                **line.zone.model_dump(),
                allocation_id=line.id,
                position=line.position,
                group=line.group,
                category=line.category,
                jar_name=line.jar_name,
                label=budget_service.allocation_label(
                    line.category.name if line.category else None, line.jar_name
                ),
                planned=line.planned,
                actual=line.actual,
                used_percent=line.used_percent,
                expected_to_date=line.expected_to_date,
                auto=zone_service.auto_detail(allocation, histories[allocation.id])
                if allocation.zone_mode == "auto"
                else None,
            )
        )
    return BudgetZoneList(
        budget_id=budget.id,
        period_month=budget.period_month,
        status=budget.status,  # type: ignore[arg-type]
        progress=status.progress,
        items=items,
    )


def _tracked_budget(db: Session, month: date) -> Budget:
    """Budget đang theo dõi của tháng (active hoặc đã đóng)."""
    budget = budget_repository.get_by_month(db, month)
    if budget is None:
        raise NotFoundError(f"Tháng {month:%m/%Y} chưa có ngân sách", "budget_not_found")
    if budget.status not in TRACKED_BUDGET_STATUSES:
        raise NotFoundError(
            f"Ngân sách tháng {month:%m/%Y} đang là nháp — kích hoạt để theo dõi",
            "budget_not_active",
        )
    return budget


def get_current_status(db: Session, today: date, month: date | None = None) -> BudgetStatusRead:
    """Status budget active/closed của `month` (mặc định tháng chứa `today`), không có → 404."""
    month = month_range(month or today)[0]
    return get_budget_status(db, _tracked_budget(db, month), today)


def _top_over(allocations: list[AllocationStatusRead]) -> AllocationStatusRead | None:
    over = [a for a in allocations if a.status == "over_budget"]
    return max(over, key=lambda a: (a.variance, -a.position), default=None)


def get_month_summary(db: Session, today: date, month: date | None = None) -> MonthSummaryRead:
    """Thu/chi/net thực tế của tháng (luôn có) + tiến độ budget nếu có budget active/closed."""
    month = month_range(month or today)[0]
    progress = month_progress(month, today)
    by_direction = transaction_repository.totals_by_direction(
        db, progress.date_from, progress.date_to
    )
    income, expense = by_direction.get("income", 0), by_direction.get("expense", 0)
    budget = budget_repository.get_by_month(db, month)
    status = (
        get_budget_status(db, budget, today)
        if budget is not None and budget.status in TRACKED_BUDGET_STATUSES
        else None
    )
    return MonthSummaryRead(
        month=month,
        progress=progress.to_read(),
        income_actual=income,
        expense_actual=expense,
        net_actual=income - expense,
        budget_id=budget.id if budget else None,
        budget_status=budget.status if budget else None,  # type: ignore[arg-type]
        budget=status.totals if status else None,
        top_over=_top_over(status.allocations) if status else None,
    )


# ---------- drill-down ----------


def list_allocation_transactions(
    db: Session, allocation_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[Transaction], int]:
    """Giao dịch chi thuộc dòng phân bổ trong tháng của budget, mới nhất trước."""
    allocation = budget_repository.get_allocation(db, allocation_id)
    if allocation is None:
        raise NotFoundError("Không tìm thấy dòng phân bổ", "allocation_not_found")
    scope = _context(db, allocation.budget).scope(allocation)
    date_from, date_to = month_range(allocation.budget.period_month)
    return transaction_repository.list_in_scope(
        db,
        date_from,
        date_to,
        scope.category_ids,
        scope.spending_types,
        offset=(page - 1) * page_size,
        limit=page_size,
    )


# ---------- review (Phase 6, 7) ----------

MAX_BUDGET_OVER_LINES = 3


@dataclass(frozen=True)
class ReviewData:
    """Metrics của kỳ + giao dịch kỳ này (để `detect_highlights` tìm cụm / khoản lớn).
    Kỳ `month` có thêm budget vs actual và phản tư của các review tuần trong tháng."""

    metrics: PeriodMetrics
    transactions: list[TxRow]
    budget: MonthlyBudgetSummary | None = None
    reflections: list[WeeklyReflectionDigest] = field(default_factory=list)


def _tx_row(t: Transaction) -> TxRow:
    return TxRow(
        id=t.id,
        occurred_on=t.occurred_on,
        direction=t.direction,
        amount=t.amount,
        note=t.note,
        category_id=t.category_id,
        category_slug=t.category.slug,
        category_name=t.category.name,
        category_icon=t.category.icon,
        spending_type=t.spending_type,
    )


def load_period_rows(db: Session, date_from: date, date_to: date) -> list[TxRow]:
    return [_tx_row(t) for t in transaction_repository.list_between(db, date_from, date_to)]


def summarize_budget(status: BudgetStatusRead) -> MonthlyBudgetSummary:
    """Rút gọn Budget vs Actual (Phase 5) cho metrics review tháng."""
    lines = [
        BudgetLineSummary(
            allocation_id=a.id,
            label=budget_service.allocation_label(
                a.category.name if a.category else None, a.jar_name
            ),
            group=a.group,
            planned=a.planned,
            actual=a.actual,
            variance=a.variance,
            used_percent=a.used_percent,
            status=a.status,
        )
        for a in sorted(status.allocations, key=lambda a: a.position)
    ]
    over = sorted(
        (line for line in lines if line.status == "over_budget"),
        key=lambda line: -line.variance,
    )
    t = status.totals
    return MonthlyBudgetSummary(
        budget_id=status.budget_id,
        status=status.status,
        strategy=status.strategy,
        expense_planned=t.expense_planned,
        expense_actual=t.expense_actual,
        expense_variance=t.expense_variance,
        unbudgeted_actual=t.unbudgeted_actual,
        over_budget_count=t.over_budget_count,
        lines=lines,
        over_lines=over[:MAX_BUDGET_OVER_LINES],
    )


def get_monthly_budget_summary(
    db: Session, month: date, today: date
) -> MonthlyBudgetSummary | None:
    """Budget vs actual của tháng nếu có budget active / closed (nháp → `None`)."""
    budget = budget_repository.get_by_month(db, month)
    if budget is None or budget.status not in TRACKED_BUDGET_STATUSES:
        return None
    return summarize_budget(get_budget_status(db, budget, today))


def get_review_metrics(db: Session, period: ReviewPeriod, start: date, today: date) -> ReviewData:
    """Thu/chi, breakdown spending_type, theo danh mục, % thay đổi so với kỳ trước."""
    rng = review_metrics.period_range(period, start)
    current = load_period_rows(db, rng.start, rng.end)
    previous = load_period_rows(db, rng.previous_start, rng.previous_end)
    metrics = review_metrics.compute_period_metrics(period, start, current, previous, today)
    if period != "month":
        return ReviewData(metrics=metrics, transactions=current)
    return ReviewData(
        metrics=metrics,
        transactions=current,
        budget=get_monthly_budget_summary(db, start, today),
        reflections=review_service.weekly_reflections_in_month(db, start),
    )


def build_review_metrics(data: ReviewData) -> ReviewMetrics:
    return review_metrics.build_review_metrics(
        data.metrics, data.transactions, budget=data.budget, reflections=data.reflections
    )


def preview_review_metrics(
    db: Session, period: ReviewPeriod, start: date, today: date
) -> ReviewMetrics:
    """Metrics đầy đủ (kèm highlights) như graph sẽ dùng — không gọi AI, không lưu."""
    return build_review_metrics(get_review_metrics(db, period, start, today))
