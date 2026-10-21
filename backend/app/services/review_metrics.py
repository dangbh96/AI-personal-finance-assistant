"""Metrics & highlights cho Weekly / Monthly review — hàm thuần, deterministic (ADR-005).

- Kỳ `week`: Thứ Hai → Chủ Nhật, so với tuần liền trước; kỳ `month`: so với tháng liền trước.
- `change_pct = round_half_up(change / previous × 100)`, `None` khi kỳ trước bằng 0.
- Highlights: top 3 danh mục chi, danh mục tăng / giảm nhiều nhất (theo đồng), cụm giao dịch lặp
  (≥ `MIN_CLUSTER_SIZE` khoản cùng danh mục + cùng buổi trong ngày, hoặc cùng từ khoá ghi chú),
  top 3 khoản chi lớn nhất.
- Riêng tháng (Phase 7, `compute_monthly_metrics`): tiết kiệm + tỉ lệ tiết kiệm, tỉ trọng
  spending_type (% 1 chữ số), chi thường xuyên vs bất thường, nguyên nhân tăng
  (`increase_driver`), khoản bất thường lớn nhất, budget vs actual, phản tư các tuần.
"""

import re
import unicodedata
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from app.core.errors import DomainError
from app.models.enums import SPENDING_TYPES
from app.schemas.review import (
    MAX_IRREGULAR_ITEMS,
    CategoryChange,
    IncreaseDriver,
    MonthlyBudgetSummary,
    MonthlyReviewMetrics,
    PeriodMetrics,
    RepeatedCluster,
    ReviewHighlights,
    ReviewMetrics,
    ReviewTransaction,
    SpendingTypeAmounts,
    SpendingTypePercents,
    TimeBucket,
    WeeklyReflectionDigest,
)
from app.services.classification_text import normalize_pattern
from app.services.money import add_months, month_range, round_vnd

TOP_CATEGORIES = 3
TOP_TRANSACTIONS = 3
MIN_CLUSTER_SIZE = 3
MAX_CLUSTERS = 3

# Từ chỉ buổi trong ngày trong ghi chú (lowercase, có dấu; "toi"/"trua" không dấu vẫn nhận).
# Không nhận "sang"/"dem" không dấu vì trùng "sang (qua)", "đem".
_TIME_WORDS: tuple[tuple[TimeBucket, frozenset[str]], ...] = (
    ("evening", frozenset({"tối", "đêm", "khuya", "toi"})),
    ("noon", frozenset({"trưa", "trua"})),
    ("morning", frozenset({"sáng"})),
)
TIME_BUCKET_LABELS: dict[TimeBucket, str] = {
    "morning": "buổi sáng",
    "noon": "buổi trưa",
    "evening": "buổi tối",
}
_WORD_RE = re.compile(r"\w+")


@dataclass(frozen=True)
class TxRow:
    """Một giao dịch đã đọc từ DB (đủ thông tin để tổng hợp, không phụ thuộc ORM)."""

    id: uuid.UUID
    occurred_on: date
    direction: str
    amount: int
    note: str | None
    category_id: uuid.UUID
    category_slug: str
    category_name: str
    category_icon: str | None
    spending_type: str | None


@dataclass(frozen=True)
class PeriodRange:
    start: date
    end: date
    previous_start: date
    previous_end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def period_range(period: str, start: date) -> PeriodRange:
    """Kỳ `week` phải bắt đầu Thứ Hai, kỳ `month` phải là ngày 1."""
    if period == "week":
        if start.weekday() != 0:
            raise DomainError("Tuần phải bắt đầu vào Thứ Hai", "week_start_not_monday")
        end = start + timedelta(days=6)
        return PeriodRange(start, end, start - timedelta(days=7), start - timedelta(days=1))
    if period == "month":
        if start.day != 1:
            raise DomainError("Tháng phải bắt đầu từ ngày 1", "month_not_first_day")
        previous_start, previous_end = month_range(add_months(start, -1))
        return PeriodRange(start, month_range(start)[1], previous_start, previous_end)
    raise DomainError(f"Kỳ review không hợp lệ: {period}", "invalid_review_period")


def change_pct(current: int, previous: int) -> int | None:
    """Phần trăm thay đổi (số nguyên, làm tròn half-up); `None` nếu kỳ trước = 0.

    >>> change_pct(2_242_000, 1_900_000)
    18
    """
    if previous <= 0:
        return None
    return round_vnd(Fraction((current - previous) * 100, previous))


def _expenses(rows: Iterable[TxRow]) -> list[TxRow]:
    return [r for r in rows if r.direction == "expense"]


def _sum(rows: Iterable[TxRow], direction: str) -> int:
    return sum(r.amount for r in rows if r.direction == direction)


def _by_spending_type(rows: Iterable[TxRow]) -> SpendingTypeAmounts:
    totals = dict.fromkeys(SPENDING_TYPES, 0)
    for r in _expenses(rows):
        if r.spending_type in totals:
            totals[r.spending_type] += r.amount
    return SpendingTypeAmounts(**totals)


def _by_category(current: Sequence[TxRow], previous: Sequence[TxRow]) -> list[CategoryChange]:
    info: dict[uuid.UUID, TxRow] = {}
    amount: Counter[uuid.UUID] = Counter()
    previous_amount: Counter[uuid.UUID] = Counter()
    count: Counter[uuid.UUID] = Counter()
    for r in _expenses(current):
        info.setdefault(r.category_id, r)
        amount[r.category_id] += r.amount
        count[r.category_id] += 1
    for r in _expenses(previous):
        info.setdefault(r.category_id, r)
        previous_amount[r.category_id] += r.amount

    changes = [
        CategoryChange(
            category_id=cid,
            slug=r.category_slug,
            name=r.category_name,
            icon=r.category_icon,
            amount=amount[cid],
            previous_amount=previous_amount[cid],
            change=amount[cid] - previous_amount[cid],
            change_pct=change_pct(amount[cid], previous_amount[cid]),
            transaction_count=count[cid],
        )
        for cid, r in info.items()
    ]
    return sorted(changes, key=lambda c: (-c.amount, -c.previous_amount, c.name))


def compute_period_metrics(
    period: str,
    start: date,
    current: Sequence[TxRow],
    previous: Sequence[TxRow],
    today: date,
) -> PeriodMetrics:
    """Tổng hợp kỳ bắt đầu `start` (giao dịch kỳ này `current`, kỳ trước `previous`)."""
    rng = period_range(period, start)
    days_elapsed = min(max((today - rng.start).days + 1, 0), rng.days)
    income, expense = _sum(current, "income"), _sum(current, "expense")
    previous_expense = _sum(previous, "expense")
    return PeriodMetrics(
        period=period,  # type: ignore[arg-type]
        period_start=rng.start,
        period_end=rng.end,
        previous_start=rng.previous_start,
        previous_end=rng.previous_end,
        as_of=min(max(today, rng.start), rng.end),
        days_elapsed=days_elapsed,
        days_in_period=rng.days,
        complete=days_elapsed == rng.days,
        income=income,
        expense=expense,
        net=income - expense,
        expense_count=len(_expenses(current)),
        previous_income=_sum(previous, "income"),
        previous_expense=previous_expense,
        expense_change=expense - previous_expense,
        expense_change_pct=change_pct(expense, previous_expense),
        by_spending_type=_by_spending_type(current),
        previous_by_spending_type=_by_spending_type(previous),
        by_category=_by_category(current, previous),
    )


# ---------- highlights ----------


def time_bucket(note: str | None) -> TimeBucket | None:
    """Buổi trong ngày nêu trong ghi chú: "Ăn tối với bạn" → `evening`."""
    if not note:
        return None
    words = set(_WORD_RE.findall(unicodedata.normalize("NFC", note).lower()))
    for bucket, markers in _TIME_WORDS:
        if words & markers:
            return bucket
    return None


def _to_review_transaction(r: TxRow) -> ReviewTransaction:
    return ReviewTransaction(
        id=r.id,
        occurred_on=r.occurred_on,
        note=r.note,
        amount=r.amount,
        category_id=r.category_id,
        category_slug=r.category_slug,
        category_name=r.category_name,
        spending_type=r.spending_type,  # type: ignore[arg-type]
    )


def _ordered(rows: Iterable[TxRow]) -> list[TxRow]:
    return sorted(rows, key=lambda r: (r.occurred_on, str(r.id)))


def _keyword_label(members: list[TxRow]) -> str:
    notes = Counter((r.note or "").strip() for r in members if (r.note or "").strip())
    if not notes:
        return members[0].category_name
    best = max(notes.values())
    # Ghi chú phổ biến nhất; bằng nhau → ghi chú xuất hiện sớm nhất.
    return next(n for r in members if notes[n := (r.note or "").strip()] == best)


def repeated_clusters(rows: Iterable[TxRow]) -> list[RepeatedCluster]:
    """Nhóm khoản chi lặp lại: ưu tiên buổi trong ngày, không có thì theo từ khoá ghi chú."""
    groups: dict[tuple[uuid.UUID, str], list[TxRow]] = {}
    buckets: dict[tuple[uuid.UUID, str], TimeBucket | None] = {}
    for r in _ordered(_expenses(rows)):
        bucket = time_bucket(r.note)
        if bucket is not None:
            key = (r.category_id, f"time:{bucket}")
        else:
            pattern = normalize_pattern(r.note or "")
            if not pattern:
                continue
            key = (r.category_id, f"kw:{pattern}")
        groups.setdefault(key, []).append(r)
        buckets[key] = bucket

    clusters = []
    for (category_id, suffix), members in groups.items():
        if len(members) < MIN_CLUSTER_SIZE:
            continue
        bucket = buckets[(category_id, suffix)]
        first = members[0]
        label = (
            f"{first.category_name} {TIME_BUCKET_LABELS[bucket]}"
            if bucket is not None
            else _keyword_label(members)
        )
        clusters.append(
            RepeatedCluster(
                key=f"{category_id}:{suffix}",
                label=label,
                category_id=category_id,
                category_slug=first.category_slug,
                category_name=first.category_name,
                time_bucket=bucket,
                count=len(members),
                total=sum(r.amount for r in members),
                transaction_ids=[r.id for r in members],
            )
        )
    clusters.sort(key=lambda c: (-c.total, -c.count, c.label))
    return clusters[:MAX_CLUSTERS]


def top_transactions(rows: Iterable[TxRow], limit: int = TOP_TRANSACTIONS) -> list[TxRow]:
    """Khoản chi lớn nhất (bằng nhau → mới hơn trước)."""
    ordered = sorted(
        _expenses(rows), key=lambda r: (-r.amount, -r.occurred_on.toordinal(), str(r.id))
    )
    return ordered[:limit]


def detect_highlights(metrics: PeriodMetrics, current: Sequence[TxRow]) -> ReviewHighlights:
    spent = [c for c in metrics.by_category if c.amount > 0]
    increases = [c for c in metrics.by_category if c.change > 0]
    decreases = [c for c in metrics.by_category if c.change < 0]
    return ReviewHighlights(
        top_categories=spent[:TOP_CATEGORIES],
        top_increase=max(increases, key=lambda c: (c.change, c.amount), default=None),
        top_decrease=min(decreases, key=lambda c: (c.change, -c.previous_amount), default=None),
        repeated_clusters=repeated_clusters(current),
        top_transactions=[_to_review_transaction(r) for r in top_transactions(current)],
    )


# ---------- riêng tháng (Phase 7) ----------


def share_pct(part: int, total: int) -> float | None:
    """`part / total × 100`, 1 chữ số thập phân (half-up); `None` nếu total ≤ 0.

    >>> share_pct(6_600_000, 25_000_000)
    26.4
    """
    if total <= 0:
        return None
    exact = Decimal(part * 100) / Decimal(total)
    return float(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def increase_driver(
    expense_change: int, irregular_change: int, previous_expense: int
) -> IncreaseDriver | None:
    """Chi tăng chủ yếu do khoản bất thường (≥ 50% mức tăng) → `irregular`, ngược lại
    `regular`; chi không tăng hoặc kỳ trước không có chi (không có mốc so sánh) → `None`."""
    if expense_change <= 0 or previous_expense <= 0:
        return None
    return "irregular" if irregular_change * 2 >= expense_change else "regular"


def irregular_items(rows: Iterable[TxRow], limit: int = MAX_IRREGULAR_ITEMS) -> list[TxRow]:
    return top_transactions((r for r in rows if r.spending_type == "irregular"), limit)


def compute_monthly_metrics(
    metrics: ReviewMetrics,
    current: Sequence[TxRow],
    budget: MonthlyBudgetSummary | None = None,
    reflections: Sequence[WeeklyReflectionDigest] = (),
) -> MonthlyReviewMetrics:
    """Bổ sung phần riêng của review tháng vào metrics chung (đã có highlights)."""
    if metrics.period != "month":
        raise ValueError("compute_monthly_metrics chỉ dùng cho kỳ month")
    current_types, previous_types = metrics.by_spending_type, metrics.previous_by_spending_type
    saved = metrics.income - metrics.expense
    previous_saved = metrics.previous_income - metrics.previous_expense
    regular = metrics.expense - current_types.irregular
    previous_regular = metrics.previous_expense - previous_types.irregular
    irregular_change = current_types.irregular - previous_types.irregular
    flagged = {f.id: f.amount for r in reflections for f in r.flagged}
    return MonthlyReviewMetrics(
        **metrics.model_dump(),
        saved=saved,
        savings_rate_pct=share_pct(saved, metrics.income),
        previous_saved=previous_saved,
        previous_savings_rate_pct=share_pct(previous_saved, metrics.previous_income),
        saved_change=saved - previous_saved,
        income_change=metrics.income - metrics.previous_income,
        income_change_pct=change_pct(metrics.income, metrics.previous_income),
        spending_type_pct=SpendingTypePercents(
            **{t: share_pct(getattr(current_types, t), metrics.expense) for t in SPENDING_TYPES}
        ),
        regular_expense=regular,
        previous_regular_expense=previous_regular,
        regular_expense_change_pct=change_pct(regular, previous_regular),
        irregular_change=irregular_change,
        increase_driver=increase_driver(
            metrics.expense_change, irregular_change, metrics.previous_expense
        ),
        irregular_items=[_to_review_transaction(r) for r in irregular_items(current)],
        budget=budget,
        weekly_reflections=list(reflections),
        flagged_count=len(flagged),
        flagged_total=sum(flagged.values()),
    )


def build_review_metrics(
    metrics: PeriodMetrics,
    current: Sequence[TxRow],
    *,
    budget: MonthlyBudgetSummary | None = None,
    reflections: Sequence[WeeklyReflectionDigest] = (),
) -> ReviewMetrics:
    """Metrics + highlights; kỳ `month` thêm phần riêng tháng (`MonthlyReviewMetrics`)."""
    review = ReviewMetrics(**metrics.model_dump(), highlights=detect_highlights(metrics, current))
    if metrics.period == "month":
        return compute_monthly_metrics(review, current, budget, reflections)
    return review
