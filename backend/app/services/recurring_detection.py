"""Phát hiện khoản định kỳ từ lịch sử giao dịch — hàm thuần, deterministic (Phase 12, ADR-005).

Thuật toán (phase-12 § 4.2):
1. Gom giao dịch theo `(direction, category_id, spending_type)`.
2. Trong mỗi nhóm tìm các cụm số tiền tương tự: mọi số trong cụm lệch ≤ ±10% so với **trung vị**
   của cụm; cần ≥ 3 lần xuất hiện. Một nhóm có thể có nhiều cụm (vd internet 300k + điện 800k).
3. Khoảng cách giữa các lần (theo ngày, cũ → mới): **weekly** nếu trung vị 5–9 ngày (7 ± 2);
   **monthly** nếu trung vị 28–31 ngày, hoặc 25–34 ngày mà ≥ 2/3 cặp liên tiếp cùng ngày trong
   tháng ± 3 (tháng liền kề).
4. `confidence = 0.4 + amount_consistency × 0.3 + interval_consistency × 0.3`, chỉ đề xuất khi
   `≥ 0.75`. `amount_consistency = 1 − (độ lệch tuyệt đối trung bình / trung vị) / 10%` (kẹp
   [0, 1]); `interval_consistency` = tỉ lệ cặp liên tiếp đúng nhịp.
5. Bỏ mẫu đã ngừng: lần cuối cách `to_date` quá 2 kỳ + 3 ngày.

Chỉ tạo **đề xuất**; user xác nhận mới thành khoản định kỳ.
"""

import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from itertools import pairwise

from app.services.money import round_vnd
from app.services.recurring_schedule import ScheduleRule, day_in_month, next_occurrence

MIN_OCCURRENCES = 3
AMOUNT_TOLERANCE_PCT = 10
MIN_CONFIDENCE = Fraction(3, 4)
WEEKLY_INTERVAL = (5, 9)
MONTHLY_INTERVAL = (28, 31)
MONTHLY_LOOSE_INTERVAL = (25, 34)
MONTHLY_DAY_TOLERANCE = 3
STALE_GRACE_DAYS = 3
_PERIOD_DAYS = {"weekly": 7, "monthly": 31}
_SUGGESTION_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "pfa:recurring-suggestion")


@dataclass(frozen=True)
class HistoryItem:
    id: uuid.UUID
    occurred_on: date
    amount: int
    direction: str
    category_id: uuid.UUID
    spending_type: str | None
    note: str | None = None


@dataclass(frozen=True)
class DetectedPattern:
    direction: str
    category_id: uuid.UUID
    spending_type: str | None
    frequency: str
    day_of_month: int | None
    day_of_week: int | None
    amount: int
    name: str | None
    amount_consistency: Fraction
    interval_consistency: Fraction
    confidence: Fraction
    median_interval_days: Fraction
    items: tuple[HistoryItem, ...]
    next_due_on: date

    @property
    def key(self) -> str:
        anchor = self.day_of_month if self.frequency == "monthly" else self.day_of_week
        return "|".join(
            [
                self.direction,
                str(self.category_id),
                self.spending_type or "-",
                self.frequency,
                str(anchor),
            ]
        )

    @property
    def suggestion_id(self) -> uuid.UUID:
        return suggestion_id_for_key(self.key)


def suggestion_id_for_key(key: str) -> uuid.UUID:
    return uuid.uuid5(_SUGGESTION_NAMESPACE, key)


# ---------- số tiền ----------


def within_tolerance(amount: int, reference: int, pct: int = AMOUNT_TOLERANCE_PCT) -> bool:
    """|amount − reference| ≤ pct% × reference (số nguyên, không float)."""
    return abs(amount - reference) * 100 <= reference * pct


def median_amount(amounts: Sequence[int]) -> int:
    """Trung vị (số chẵn phần tử → trung bình 2 số giữa, làm tròn tới đồng)."""
    if not amounts:
        raise ValueError("amounts rỗng")
    ordered = sorted(amounts)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round_vnd(Fraction(ordered[mid - 1] + ordered[mid], 2))


def amount_consistency(amounts: Sequence[int], median: int) -> Fraction:
    if median <= 0:
        return Fraction(0)
    deviation = Fraction(sum(abs(a - median) for a in amounts), len(amounts) * median)
    return max(Fraction(0), 1 - deviation * 100 / AMOUNT_TOLERANCE_PCT)


def _settle_cluster(items: Sequence[HistoryItem], pivot: int) -> list[HistoryItem]:
    """Lặp: lấy các khoản quanh `pivot` → trung vị → lấy lại quanh trung vị, tới khi ổn định."""
    members = [i for i in items if within_tolerance(i.amount, pivot)]
    for _ in range(5):
        if not members:
            return []
        median = median_amount([m.amount for m in members])
        settled = [i for i in items if within_tolerance(i.amount, median)]
        if settled == members:
            break
        members = settled
    if not members:
        return []
    median = median_amount([m.amount for m in members])
    return [m for m in members if within_tolerance(m.amount, median)]


def amount_clusters(items: Sequence[HistoryItem]) -> list[list[HistoryItem]]:
    """Các cụm số tiền tương tự (≥ 3 khoản), cụm lớn nhất trước; mỗi khoản thuộc tối đa 1 cụm."""
    remaining = sorted(items, key=lambda i: (i.occurred_on, i.amount, str(i.id)))
    clusters: list[list[HistoryItem]] = []
    while len(remaining) >= MIN_OCCURRENCES:
        best: list[HistoryItem] = []
        for pivot in sorted({i.amount for i in remaining}):
            members = _settle_cluster(remaining, pivot)
            if len(members) > len(best) or (
                len(members) == len(best)
                and members
                and members[-1].occurred_on > best[-1].occurred_on
            ):
                best = members
        if len(best) < MIN_OCCURRENCES:
            break
        clusters.append(best)
        taken = {i.id for i in best}
        remaining = [i for i in remaining if i.id not in taken]
    return clusters


# ---------- khoảng cách ----------


def _median_fraction(values: Sequence[int]) -> Fraction:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[mid])
    return Fraction(ordered[mid - 1] + ordered[mid], 2)


def _month_gap(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _monthly_pair_ok(a: date, b: date) -> bool:
    delta = (b - a).days
    if MONTHLY_INTERVAL[0] <= delta <= MONTHLY_INTERVAL[1]:
        return True
    return _month_gap(a, b) == 1 and abs(a.day - b.day) <= MONTHLY_DAY_TOLERANCE


def classify_interval(dates: Sequence[date]) -> tuple[str | None, Fraction, Fraction]:
    """`(frequency | None, interval_consistency, median_interval_days)` của các ngày đã sort."""
    if len(dates) < 2:
        return None, Fraction(0), Fraction(0)
    pairs = list(pairwise(dates))
    deltas = [(b - a).days for a, b in pairs]
    median = _median_fraction(deltas)
    weekly_ok = [abs(d - 7) <= 2 for d in deltas]
    monthly_ok = [_monthly_pair_ok(a, b) for a, b in pairs]
    if WEEKLY_INTERVAL[0] <= median <= WEEKLY_INTERVAL[1]:
        return "weekly", Fraction(sum(weekly_ok), len(pairs)), median
    monthly_share = Fraction(sum(monthly_ok), len(pairs))
    if MONTHLY_INTERVAL[0] <= median <= MONTHLY_INTERVAL[1] or (
        MONTHLY_LOOSE_INTERVAL[0] <= median <= MONTHLY_LOOSE_INTERVAL[1]
        and monthly_share >= Fraction(2, 3)
    ):
        return "monthly", monthly_share, median
    return None, Fraction(0), median


def infer_day_of_month(dates: Sequence[date]) -> int:
    """Ngày trong tháng khớp nhất: tổng lệch nhỏ nhất (ngày gốc kẹp về cuối tháng ngắn), rồi nhiều
    lần khớp đúng nhất, rồi ngày của lần gần nhất. Vd 31/07, 31/08, 30/09 → 31."""
    latest = dates[-1].day

    def score(candidate: int) -> tuple[int, int, int, int]:
        clamped = [day_in_month(d.year, d.month, candidate).day for d in dates]
        distance = sum(abs(c - d.day) for c, d in zip(clamped, dates, strict=True))
        exact = sum(c == d.day for c, d in zip(clamped, dates, strict=True))
        return (distance, -exact, 0 if candidate == latest else 1, -candidate)

    return min({d.day for d in dates}, key=score)


def infer_day_of_week(dates: Sequence[date]) -> int:
    counts = Counter(d.isoweekday() for d in dates)
    latest = dates[-1].isoweekday()
    return max(counts, key=lambda wd: (counts[wd], wd == latest, -wd))


def _common_note(items: Sequence[HistoryItem]) -> str | None:
    notes = [(i.note or "").strip() for i in items]
    counts = Counter(n for n in notes if n)
    if not counts:
        return None
    last_seen = {n: idx for idx, n in enumerate(notes) if n}
    return max(counts, key=lambda n: (counts[n], last_seen[n]))


# ---------- tổng hợp ----------


def _group_key(item: HistoryItem) -> tuple[str, uuid.UUID, str | None]:
    return item.direction, item.category_id, item.spending_type


def evaluate_cluster(
    cluster: Sequence[HistoryItem], *, to_date: date, today: date
) -> DetectedPattern | None:
    items = sorted(cluster, key=lambda i: (i.occurred_on, str(i.id)))
    if len(items) < MIN_OCCURRENCES:
        return None
    dates = [i.occurred_on for i in items]
    frequency, interval_c, median_interval = classify_interval(dates)
    if frequency is None:
        return None
    if (to_date - dates[-1]).days > 2 * _PERIOD_DAYS[frequency] + STALE_GRACE_DAYS:
        return None
    amounts = [i.amount for i in items]
    median = median_amount(amounts)
    amount_c = amount_consistency(amounts, median)
    confidence = Fraction(2, 5) + amount_c * Fraction(3, 10) + interval_c * Fraction(3, 10)
    if confidence < MIN_CONFIDENCE:
        return None
    if frequency == "weekly":
        rule = ScheduleRule("weekly", day_of_week=infer_day_of_week(dates))
    else:
        rule = ScheduleRule("monthly", day_of_month=infer_day_of_month(dates))
    first = items[0]
    return DetectedPattern(
        direction=first.direction,
        category_id=first.category_id,
        spending_type=first.spending_type,
        frequency=frequency,
        day_of_month=rule.day_of_month,
        day_of_week=rule.day_of_week,
        amount=median,
        name=_common_note(items),
        amount_consistency=amount_c,
        interval_consistency=interval_c,
        confidence=confidence,
        median_interval_days=median_interval,
        items=tuple(items),
        next_due_on=next_occurrence(rule, max(dates[-1], today)),
    )


def detect_patterns(
    items: Iterable[HistoryItem], *, to_date: date, today: date
) -> list[DetectedPattern]:
    """Mẫu định kỳ đủ tin cậy, sắp theo confidence giảm dần rồi số tiền giảm dần."""
    groups: dict[tuple[str, uuid.UUID, str | None], list[HistoryItem]] = {}
    for item in items:
        groups.setdefault(_group_key(item), []).append(item)
    patterns: list[DetectedPattern] = []
    for key in sorted(groups, key=lambda k: (k[0], str(k[1]), k[2] or "")):
        for cluster in amount_clusters(groups[key]):
            pattern = evaluate_cluster(cluster, to_date=to_date, today=today)
            if pattern is not None:
                patterns.append(pattern)
    patterns.sort(key=lambda p: (-p.confidence, -p.amount, p.key))
    return patterns
