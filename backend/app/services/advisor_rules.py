"""Budget adjustment advisor — decision tree deterministic (Phase 8, ADR-005). Không gọi AI.

Đúng sơ đồ trong docs/architecture/budget-adjustment.md § 1, ngưỡng lấy từ
`app_settings.budget_advisor` (mặc định 60% / 15% / 3 tháng / làm tròn 100.000đ):

1. `actual <= comfort_high` (vùng linh hoạt Phase 9 đã lưu; dòng chưa có vùng → `planned`)
   → `on_track`.
2. Giao dịch `irregular` (cộng lại) **hoặc** một giao dịch đơn lẻ chiếm `>= 60%` phần vượt
   → `one_off` (chỉ ra giao dịch ngoại lệ, không đề xuất planned mới).
3. Chưa đủ `3` tháng có dữ liệu (tính cả tháng đang xét) → `adjust_behavior`.
4. `3` tháng gần nhất đều vượt `planned` **và** CV của actual `<= 15%` → `adjust_budget`,
   planned đề xuất = median(3 tháng) làm tròn `100.000đ`.
5. Còn lại → `adjust_behavior`.

CV = độ lệch chuẩn **tổng thể** (population std, chia cho n) / trung bình. So sánh ngưỡng làm
trên số hữu tỉ (`CV² <= ngưỡng²`) nên không phụ thuộc sai số float.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

from app.models.enums import AdviceVerdict
from app.schemas.budget_advice import (
    AdviceHistoryMonth,
    AdviceRule,
    AdviceTransaction,
    AdvisorSettings,
    BudgetAdviceEvidence,
)
from app.schemas.zone import ZoneEvidence
from app.services.money import round_vnd

DEFAULT_SETTINGS = AdvisorSettings(
    one_off_share_threshold=0.6,
    stable_cv_threshold=0.15,
    min_history_months=3,
    budget_rounding_step=100_000,
)


@dataclass(frozen=True)
class Thresholds:
    one_off_share: Fraction
    stable_cv: Fraction
    min_history_months: int
    rounding_step: int

    @classmethod
    def from_settings(cls, settings: AdvisorSettings) -> "Thresholds":
        # Fraction(str(0.6)) = 3/5 đúng tuyệt đối (không phải 0.59999…).
        return cls(
            one_off_share=Fraction(str(settings.one_off_share_threshold)),
            stable_cv=Fraction(str(settings.stable_cv_threshold)),
            min_history_months=settings.min_history_months,
            rounding_step=settings.budget_rounding_step,
        )


DEFAULT_THRESHOLDS = Thresholds.from_settings(DEFAULT_SETTINGS)


@dataclass(frozen=True)
class ScopeTransaction:
    """Một giao dịch chi thuộc phạm vi dòng phân bổ trong tháng đang xét."""

    id: uuid.UUID
    occurred_on: date
    note: str | None
    amount: int
    category_name: str
    spending_type: str | None


@dataclass(frozen=True)
class MonthActual:
    month: date
    actual: int
    transaction_count: int


@dataclass(frozen=True)
class AdviceInput:
    label: str
    group: str
    category_slug: str | None
    month: date
    as_of: date
    month_complete: bool
    planned: int
    actual: int
    comfort_high: int | None
    transactions: Sequence[ScopeTransaction]
    history: Sequence[MonthActual]
    """Các tháng gần nhất, cũ nhất trước, **tính cả** tháng đang xét (phần tử cuối)."""
    zone: ZoneEvidence | None = None
    """Vùng linh hoạt của dòng (Phase 9) nếu đã có ngưỡng — chỉ đưa vào evidence."""


@dataclass(frozen=True)
class AdviceResult:
    verdict: AdviceVerdict
    evidence: BudgetAdviceEvidence


# ---------- helper thuần ----------


def median(values: Sequence[int]) -> Fraction:
    """Trung vị (n chẵn → trung bình 2 giá trị giữa).

    >>> median([4_400_000, 4_600_000, 4_500_000])
    Fraction(4500000, 1)
    """
    if not values:
        raise ValueError("median cần ít nhất 1 giá trị")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[mid])
    return Fraction(ordered[mid - 1] + ordered[mid], 2)


def cv_squared(values: Sequence[int]) -> Fraction | None:
    """(population std / mean)² — chính xác tuyệt đối; `None` nếu rỗng hoặc mean <= 0."""
    if not values:
        return None
    n = len(values)
    mean = Fraction(sum(values), n)
    if mean <= 0:
        return None
    variance = sum((Fraction(v) - mean) ** 2 for v in values) / n
    return variance / (mean * mean)


def _quantize(value: Decimal, digits: int) -> float:
    return float(value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def _sqrt(value: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 40
        return (Decimal(value.numerator) / Decimal(value.denominator)).sqrt()


def round_proposed(value: Fraction, step: int) -> int:
    """Làm tròn planned đề xuất tới bội số `step` gần nhất (nửa làm tròn lên)."""
    return round_vnd(value, step)


def _ratio(numerator: int, denominator: int) -> Fraction | None:
    if denominator <= 0:
        return None
    return Fraction(numerator, denominator)


def _share(value: Fraction | None) -> tuple[float | None, float | None]:
    """Tỉ lệ (tối đa 1) dạng `(0..1 với 4 chữ số, % với 1 chữ số)`."""
    if value is None:
        return None, None
    capped = min(value, Fraction(1))
    exact = Decimal(capped.numerator) / Decimal(capped.denominator)
    return _quantize(exact, 4), _quantize(exact * 100, 1)


def _pct(value: Fraction) -> float:
    return _quantize(Decimal(value.numerator) * 100 / Decimal(value.denominator), 1)


def _tx(t: ScopeTransaction | None) -> AdviceTransaction | None:
    if t is None:
        return None
    return AdviceTransaction(
        transaction_id=t.id,
        occurred_on=t.occurred_on,
        note=t.note,
        amount=t.amount,
        category_name=t.category_name,
        spending_type=t.spending_type,  # type: ignore[arg-type]
    )


def _largest(transactions: Sequence[ScopeTransaction]) -> ScopeTransaction | None:
    """Giao dịch lớn nhất (bằng nhau → giao dịch mới hơn)."""
    return max(transactions, key=lambda t: (t.amount, t.occurred_on), default=None)


# ---------- decision tree ----------


def evaluate(inp: AdviceInput, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> AdviceResult:
    n = thresholds.min_history_months
    threshold = inp.comfort_high if inp.comfort_high is not None else inp.planned
    over = max(0, inp.actual - threshold)

    largest = _largest(inp.transactions)
    irregular = [t for t in inp.transactions if t.spending_type == "irregular"]
    irregular_total = sum(t.amount for t in irregular)
    largest_irregular = _largest(irregular)
    single_share = _ratio(largest.amount, over) if largest and over else None
    irregular_share = _ratio(irregular_total, over) if irregular_total and over else None
    one_off_by_irregular = (
        irregular_share is not None and irregular_share >= thresholds.one_off_share
    )
    one_off_by_single = single_share is not None and single_share >= thresholds.one_off_share

    history = list(inp.history)[-n:]
    values = [h.actual for h in history]
    history_months = sum(1 for h in history if h.transaction_count > 0)
    all_over = len(history) == n and all(v > inp.planned for v in values)
    cv2 = cv_squared(values) if len(history) == n else None
    med = median(values) if len(history) == n else None

    rule: AdviceRule
    verdict: AdviceVerdict
    one_off_tx: ScopeTransaction | None = None
    proposed: int | None = None
    if inp.actual <= threshold:
        verdict, rule = "on_track", "within_plan"
    elif one_off_by_irregular:
        verdict, rule, one_off_tx = "one_off", "one_off_irregular", largest_irregular
    elif one_off_by_single:
        verdict, rule, one_off_tx = "one_off", "one_off_single_transaction", largest
    elif history_months < n:
        verdict, rule = "adjust_behavior", "insufficient_history"
    elif all_over and cv2 is not None and cv2 <= thresholds.stable_cv**2:
        assert med is not None
        verdict, rule = "adjust_budget", "stable_overspend"
        proposed = round_proposed(med, thresholds.rounding_step)
    else:
        verdict, rule = "adjust_behavior", "unstable_overspend"

    single_share_value, single_share_pct = _share(single_share)
    irregular_share_value, irregular_share_pct = _share(irregular_share)
    cv_value = None if cv2 is None else _quantize(_sqrt(cv2), 4)
    cv_pct = None if cv2 is None else _quantize(_sqrt(cv2) * 100, 1)
    return AdviceResult(
        verdict=verdict,
        evidence=BudgetAdviceEvidence(
            allocation_label=inp.label,
            group=inp.group,  # type: ignore[arg-type]
            category_slug=inp.category_slug,
            month=inp.month,
            as_of=inp.as_of,
            month_complete=inp.month_complete,
            planned_amount=inp.planned,
            actual_amount=inp.actual,
            variance=inp.actual - inp.planned,
            comfort_high=inp.comfort_high,
            comfort_high_used=inp.comfort_high is not None,
            threshold_amount=threshold,
            over_amount=over,
            transaction_count=len(inp.transactions),
            largest_transaction=_tx(largest),
            single_transaction_share=single_share_value,
            single_transaction_share_pct=single_share_pct,
            irregular_total=irregular_total,
            irregular_share=irregular_share_value,
            irregular_share_pct=irregular_share_pct,
            irregular_transaction=_tx(largest_irregular),
            one_off_transaction=_tx(one_off_tx),
            history_actuals=[
                AdviceHistoryMonth(
                    month=h.month,
                    actual=h.actual,
                    transaction_count=h.transaction_count,
                    has_data=h.transaction_count > 0,
                    over_planned=h.actual > inp.planned,
                )
                for h in history
            ],
            history_months=history_months,
            min_history_months=n,
            all_over_planned=all_over,
            cv=cv_value,
            cv_pct=cv_pct,
            history_median=None if med is None else round_vnd(med),
            proposed_planned_amount=proposed,
            one_off_share_threshold_pct=_pct(thresholds.one_off_share),
            stable_cv_threshold_pct=_pct(thresholds.stable_cv),
            budget_rounding_step=thresholds.rounding_step,
            rule=rule,
            zone=inp.zone,
        ),
    )
