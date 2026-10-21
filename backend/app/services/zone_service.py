"""Flexible budget zones (Phase 9) — deterministic, không gọi AI (ADR-005). Tiền là số nguyên đồng.

Công thức theo docs/architecture/budget-adjustment.md § 2:

- `manual`: user nhập đủ 3 ngưỡng, `comfort_low <= comfort_high <= warning_threshold`.
- `auto` khi có >= 3 tháng dữ liệu trong 6 tháng **trước** tháng ngân sách (tháng có dữ liệu = có
  ít nhất 1 giao dịch chi trong phạm vi dòng; giá trị của tháng = chi tiêu **không tính** giao dịch
  `irregular`; dùng tối đa 6 tháng gần nhất có dữ liệu):
  `comfort_high = max(planned, mean + 0.5*std)`, `warning_threshold = max(planned*1.1, mean + std)`,
  `comfort_low = planned*0.875` — `std` là độ lệch chuẩn tổng thể (chia n).
- `auto` thiếu dữ liệu, hoặc dòng nhóm `irregular` (chỉ gồm khoản bất thường nên không có "nhịp"
  để học): `comfort_low = 0.875*planned`, `comfort_high = 1.125*planned`,
  `warning_threshold = 1.25*planned`.
- Ngưỡng lẻ làm tròn tới **đồng** gần nhất (`round_vnd`, half-up) — không làm tròn 100.000đ.

Trạng thái vùng của một tháng: `normal` nếu `actual <= comfort_high`, `attention` nếu
`actual <= warning_threshold`, còn lại `review_needed`. Dòng `auto` chưa tính (ngưỡng NULL) → zone
`None`. Nhóm `savings` không theo dõi chi tiêu nên không có vùng.

Pro-rata (cảnh báo sớm): tháng đang chạy và `actual / planned` vượt `ngày đã qua / số ngày trong
tháng` hơn 10 điểm % (cùng dung sai với `pace_status` Phase 5) → `early_warning`, **không** đổi
zone.

Ngưỡng auto được lưu vào cột (cache) khi user bấm tính lại hoặc chuyển sang auto; advisor
(Phase 8) đọc `comfort_high` đã lưu. Tính lại là idempotent: cùng dữ liệu → cùng ngưỡng.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import Budget, BudgetAllocation
from app.models.enums import ZoneStatus
from app.repositories import budget_repository, transaction_repository
from app.schemas.zone import (
    AllocationZoneRead,
    AutoZoneBasis,
    AutoZoneDetailRead,
    AutoZoneFallbackReason,
    ZoneEvidence,
    ZoneHistoryMonthRead,
    ZoneThresholdsRead,
    ZoneUpdate,
)
from app.services import budget_service
from app.services.budget_service import AllocationScope
from app.services.money import add_months, elapsed_days, format_vnd, month_range, round_vnd

MIN_HISTORY_MONTHS = 3
MAX_HISTORY_MONTHS = 6
EARLY_WARNING_TOLERANCE = Fraction(10, 100)
COMFORT_LOW_RATIO = Fraction(7, 8)  # 0.875
FALLBACK_HIGH_RATIO = Fraction(9, 8)  # 1.125
FALLBACK_WARNING_RATIO = Fraction(5, 4)  # 1.25
AUTO_WARNING_MIN_RATIO = Fraction(11, 10)  # 1.1

# (category_id, spending_type, tổng tiền, số giao dịch) — aggregate chi tiêu của 1 tháng.
ExpenseRow = tuple[uuid.UUID, str | None, int, int]


class _ZoneLike(Protocol):
    group: str
    planned_amount: int
    zone_mode: str
    comfort_low: int | None
    comfort_high: int | None
    warning_threshold: int | None


# ---------- tính toán thuần (không đụng DB) ----------


@dataclass(frozen=True)
class ZoneThresholds:
    comfort_low: int
    comfort_high: int
    warning_threshold: int

    def to_read(self) -> ZoneThresholdsRead:
        return ZoneThresholdsRead(
            comfort_low=self.comfort_low,
            comfort_high=self.comfort_high,
            warning_threshold=self.warning_threshold,
        )


@dataclass(frozen=True)
class HistoryMonth:
    month: date
    actual: int
    """Chi trong phạm vi dòng, không tính giao dịch `irregular`."""
    irregular: int
    transaction_count: int

    @property
    def has_data(self) -> bool:
        return self.transaction_count > 0


@dataclass(frozen=True)
class AutoZone:
    thresholds: ZoneThresholds
    basis: AutoZoneBasis
    fallback_reason: AutoZoneFallbackReason | None
    history: tuple[HistoryMonth, ...]
    used_months: frozenset[date]
    mean: Fraction | None
    std: Decimal | None


@dataclass(frozen=True)
class ZoneReading:
    zone: ZoneStatus | None
    early_warning: bool
    early_warning_message: str | None
    expected_to_date: int


def _decimal(value: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 40
        return Decimal(value.numerator) / Decimal(value.denominator)


def history_stats(values: Sequence[int]) -> tuple[Fraction, Decimal]:
    """`(mean, population std)` — mean chính xác, std căn bậc hai với 40 chữ số.

    >>> history_stats([3_800_000, 4_200_000, 4_000_000])[0]
    Fraction(4000000, 1)
    """
    if not values:
        raise ValueError("history_stats cần ít nhất 1 giá trị")
    n = len(values)
    mean = Fraction(sum(values), n)
    variance = sum((Fraction(v) - mean) ** 2 for v in values) / n
    with localcontext() as ctx:
        ctx.prec = 40
        std = _decimal(variance).sqrt()
    return mean, std


def fallback_thresholds(planned: int) -> ZoneThresholds:
    """Thiếu lịch sử: 0.875 / 1.125 / 1.25 × planned, làm tròn tới đồng."""
    return ZoneThresholds(
        comfort_low=round_vnd(planned * COMFORT_LOW_RATIO),
        comfort_high=round_vnd(planned * FALLBACK_HIGH_RATIO),
        warning_threshold=round_vnd(planned * FALLBACK_WARNING_RATIO),
    )


def history_thresholds(planned: int, values: Sequence[int]) -> ZoneThresholds:
    """Đủ lịch sử: `max(planned, mean + 0.5*std)` / `max(planned*1.1, mean + std)` /
    `planned*0.875`, làm tròn tới đồng."""
    mean, std = history_stats(values)
    with localcontext() as ctx:
        ctx.prec = 40
        mean_d = _decimal(mean)
        comfort = mean_d + std / 2
        warning = mean_d + std
    return ZoneThresholds(
        comfort_low=round_vnd(planned * COMFORT_LOW_RATIO),
        comfort_high=max(planned, round_vnd(comfort)),
        warning_threshold=max(round_vnd(planned * AUTO_WARNING_MIN_RATIO), round_vnd(warning)),
    )


def calculate_auto_zone_from_history(
    planned: int, history: Sequence[HistoryMonth], *, group: str
) -> AutoZone:
    """Ngưỡng auto từ các tháng trước tháng ngân sách (cũ nhất trước)."""
    months = tuple(history)
    if group == "irregular":
        return AutoZone(
            fallback_thresholds(planned),
            "fallback",
            "irregular_group",
            months,
            frozenset(),
            None,
            None,
        )
    with_data = [h for h in months if h.has_data][-MAX_HISTORY_MONTHS:]
    if len(with_data) < MIN_HISTORY_MONTHS:
        return AutoZone(
            fallback_thresholds(planned),
            "fallback",
            "insufficient_history",
            months,
            frozenset(),
            None,
            None,
        )
    values = [h.actual for h in with_data]
    mean, std = history_stats(values)
    return AutoZone(
        history_thresholds(planned, values),
        "history",
        None,
        months,
        frozenset(h.month for h in with_data),
        mean,
        std,
    )


def validate_manual_thresholds(
    comfort_low: int | None, comfort_high: int | None, warning_threshold: int | None
) -> ZoneThresholds:
    """Manual mode: đủ 3 ngưỡng và `comfort_low <= comfort_high <= warning_threshold`."""
    if comfort_low is None or comfort_high is None or warning_threshold is None:
        raise DomainError(
            "Chế độ thủ công cần đủ 3 ngưỡng: mức dưới, mức trên vùng thoải mái và ngưỡng cảnh báo",
            "zone_thresholds_required",
        )
    if comfort_low > comfort_high:
        raise DomainError(
            f"Mức dưới vùng thoải mái ({format_vnd(comfort_low)}) phải nhỏ hơn hoặc bằng mức trên "
            f"({format_vnd(comfort_high)})",
            "invalid_zone_thresholds",
        )
    if comfort_high > warning_threshold:
        raise DomainError(
            f"Mức trên vùng thoải mái ({format_vnd(comfort_high)}) phải nhỏ hơn hoặc bằng ngưỡng "
            f"cảnh báo ({format_vnd(warning_threshold)})",
            "invalid_zone_thresholds",
        )
    return ZoneThresholds(comfort_low, comfort_high, warning_threshold)


def zone_for(actual: int, thresholds: ZoneThresholds) -> ZoneStatus:
    if actual <= thresholds.comfort_high:
        return "normal"
    if actual <= thresholds.warning_threshold:
        return "attention"
    return "review_needed"


def _pct_text(value: Fraction) -> str:
    """`Fraction(4, 5)` → `80`, `Fraction(15, 31)` → `48,4` (1 chữ số, half-up, dấu phẩy)."""
    pct = _decimal(value * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = f"{pct:f}".removesuffix(".0")
    return text.replace(".", ",")


def pro_rata(actual: int, planned: int, elapsed: int, days_in_month: int) -> tuple[int, str | None]:
    """`(expected_to_date, early_warning_message | None)`.

    Cảnh báo khi tháng đang chạy (0 < ngày đã qua < số ngày) và % đã dùng vượt % tháng đã qua
    hơn `EARLY_WARNING_TOLERANCE`.
    """
    progress = Fraction(elapsed, days_in_month)
    expected = round_vnd(planned * progress)
    if planned <= 0 or not 0 < elapsed < days_in_month:
        return expected, None
    used = Fraction(actual, planned)
    if used - progress <= EARLY_WARNING_TOLERANCE:
        return expected, None
    return expected, (
        f"Đã dùng {_pct_text(used)}% ngân sách khi mới qua {_pct_text(progress)}% tháng"
    )


def stored_thresholds(allocation: _ZoneLike) -> ZoneThresholds | None:
    """Ngưỡng đã lưu; `None` nếu dòng auto chưa được tính."""
    if (
        allocation.comfort_low is None
        or allocation.comfort_high is None
        or allocation.warning_threshold is None
    ):
        return None
    return ZoneThresholds(
        allocation.comfort_low, allocation.comfort_high, allocation.warning_threshold
    )


def zone_reading(
    actual: int, allocation: _ZoneLike, elapsed: int, days_in_month: int
) -> ZoneReading:
    thresholds = stored_thresholds(allocation)
    expected, message = pro_rata(actual, allocation.planned_amount, elapsed, days_in_month)
    return ZoneReading(
        zone=zone_for(actual, thresholds) if thresholds else None,
        early_warning=message is not None,
        early_warning_message=message,
        expected_to_date=expected,
    )


def get_zone_status(actual: int, allocation: _ZoneLike, today: date, month: date) -> ZoneReading:
    """Zone của `actual` theo ngưỡng đã lưu + pro-rata của `month` tính tới `today`."""
    return zone_reading(actual, allocation, elapsed_days(month, today), month_range(month)[1].day)


def allocation_zone(
    allocation: _ZoneLike, actual: int, elapsed: int, days_in_month: int
) -> AllocationZoneRead | None:
    """Vùng hiển thị cạnh Budget vs Actual; nhóm savings → `None`."""
    if allocation.group == "savings":
        return None
    reading = zone_reading(actual, allocation, elapsed, days_in_month)
    return AllocationZoneRead(
        zone_mode=allocation.zone_mode,  # type: ignore[arg-type]
        comfort_low=allocation.comfort_low,
        comfort_high=allocation.comfort_high,
        warning_threshold=allocation.warning_threshold,
        calculated=stored_thresholds(allocation) is not None,
        zone=reading.zone,
        early_warning=reading.early_warning,
        early_warning_message=reading.early_warning_message,
    )


def zone_evidence(
    allocation: _ZoneLike, actual: int, elapsed: int, days_in_month: int
) -> ZoneEvidence | None:
    """Evidence vùng cho advisor (Phase 8) — chỉ khi dòng đã có ngưỡng."""
    thresholds = stored_thresholds(allocation)
    if allocation.group == "savings" or thresholds is None:
        return None
    reading = zone_reading(actual, allocation, elapsed, days_in_month)
    assert reading.zone is not None
    return ZoneEvidence(
        zone_mode=allocation.zone_mode,  # type: ignore[arg-type]
        planned_amount=allocation.planned_amount,
        comfort_low=thresholds.comfort_low,
        comfort_high=thresholds.comfort_high,
        warning_threshold=thresholds.warning_threshold,
        actual_amount=actual,
        zone=reading.zone,
        early_warning=reading.early_warning,
    )


def auto_detail(allocation: _ZoneLike, history: Sequence[HistoryMonth]) -> AutoZoneDetailRead:
    """Giải thích ngưỡng auto: tính lại từ dữ liệu hiện tại, so với ngưỡng đã lưu."""
    auto = calculate_auto_zone_from_history(
        allocation.planned_amount, history, group=allocation.group
    )
    stored = stored_thresholds(allocation)
    return AutoZoneDetailRead(
        basis=auto.basis,
        fallback_reason=auto.fallback_reason,
        min_history_months=MIN_HISTORY_MONTHS,
        max_history_months=MAX_HISTORY_MONTHS,
        history_months=len(auto.used_months),
        history=[
            ZoneHistoryMonthRead(
                month=h.month,
                actual=h.actual,
                irregular_excluded=h.irregular,
                transaction_count=h.transaction_count,
                has_data=h.has_data,
                used=h.month in auto.used_months,
            )
            for h in auto.history
        ],
        mean=None if auto.mean is None else round_vnd(auto.mean),
        std=None if auto.std is None else round_vnd(auto.std),
        suggested=auto.thresholds.to_read(),
        stale=stored is not None and stored != auto.thresholds,
    )


# ---------- lịch sử (DB) ----------


def history_months(month: date) -> list[date]:
    """`MAX_HISTORY_MONTHS` tháng trước `month`, cũ nhất trước."""
    first = month_range(month)[0]
    return [add_months(first, -k) for k in range(MAX_HISTORY_MONTHS, 0, -1)]


def scope_history(
    scope: AllocationScope, rows_by_month: Mapping[date, Iterable[ExpenseRow]]
) -> list[HistoryMonth]:
    """Chi tiêu từng tháng trong phạm vi dòng, tách phần `irregular`."""
    result = []
    for month, rows in rows_by_month.items():
        regular = irregular = count = 0
        for category_id, spending_type, amount, n in rows:
            if category_id in scope.category_ids or spending_type in scope.spending_types:
                count += n
                if spending_type == "irregular":
                    irregular += amount
                else:
                    regular += amount
        result.append(HistoryMonth(month, regular, irregular, count))
    return result


def _jar_ids(db: Session, budget: Budget) -> dict[str, list[uuid.UUID]]:
    if budget.strategy != "envelope":
        return {}
    jars = budget_service.load_jar_categories(db)
    return {name: [c.id for c in cats] for name, cats in jars.items()}


def load_histories(
    db: Session,
    budget: Budget,
    allocations: Sequence[BudgetAllocation],
    month: date | None = None,
) -> dict[uuid.UUID, list[HistoryMonth]]:
    """Lịch sử 6 tháng trước tháng ngân sách của các dòng (bỏ nhóm savings)."""
    targets = [a for a in allocations if a.group != "savings"]
    if not targets:
        return {}
    rows_by_month = {
        m: transaction_repository.expense_totals_by_category_and_spending_type(db, *month_range(m))
        for m in history_months(month or budget.period_month)
    }
    jar_ids = _jar_ids(db, budget)
    return {
        a.id: scope_history(
            budget_service.allocation_scope(budget.strategy, a, jar_ids), rows_by_month
        )
        for a in targets
    }


def calculate_auto_zone(
    db: Session, allocation: BudgetAllocation, month: date | None = None
) -> AutoZone:
    """Ngưỡng auto của dòng cho `month` (mặc định tháng của budget) — không ghi DB."""
    budget = allocation.budget
    history = load_histories(db, budget, [allocation], month).get(allocation.id, [])
    return calculate_auto_zone_from_history(
        allocation.planned_amount, history, group=allocation.group
    )


# ---------- cập nhật ----------


def _apply(allocation: BudgetAllocation, thresholds: ZoneThresholds) -> None:
    allocation.comfort_low = thresholds.comfort_low
    allocation.comfort_high = thresholds.comfort_high
    allocation.warning_threshold = thresholds.warning_threshold


def _ensure_tracked(allocation: BudgetAllocation) -> None:
    if allocation.group == "savings":
        raise DomainError(
            "Dòng tiết kiệm không theo dõi chi tiêu nên không có vùng linh hoạt",
            "allocation_not_tracked",
        )


def _ensure_editable(budget: Budget) -> None:
    if budget.status == "closed":
        raise ConflictError(
            f"Ngân sách tháng {budget.period_month:%m/%Y} đã đóng — mở lại trước khi chỉnh vùng",
            "budget_closed",
        )


def update_zone(db: Session, allocation_id: uuid.UUID, data: ZoneUpdate) -> BudgetAllocation:
    """`manual` → lưu 3 ngưỡng user nhập (đã validate); `auto` → tính lại ngay và lưu cache."""
    allocation = budget_repository.get_allocation(db, allocation_id)
    if allocation is None:
        raise NotFoundError("Không tìm thấy dòng phân bổ", "allocation_not_found")
    _ensure_tracked(allocation)
    _ensure_editable(allocation.budget)
    if data.zone_mode == "manual":
        thresholds = validate_manual_thresholds(
            data.comfort_low, data.comfort_high, data.warning_threshold
        )
    else:
        if any(
            v is not None for v in (data.comfort_low, data.comfort_high, data.warning_threshold)
        ):
            raise DomainError(
                "Chế độ tự động không nhận ngưỡng nhập tay — chọn chế độ thủ công để tự đặt ngưỡng",
                "zone_thresholds_not_allowed",
            )
        thresholds = calculate_auto_zone(db, allocation).thresholds
    allocation.zone_mode = data.zone_mode
    _apply(allocation, thresholds)
    db.flush()
    db.commit()
    db.refresh(allocation)
    return allocation


def recalculate_auto_zones(
    db: Session, budget_id: uuid.UUID, allocation_ids: Sequence[uuid.UUID] | None = None
) -> Budget:
    """Tính lại và lưu ngưỡng các dòng `auto` (mặc định mọi dòng chi tiêu); dòng `manual` giữ
    nguyên. Idempotent."""
    budget = budget_service.get_budget(db, budget_id)
    _ensure_editable(budget)
    rows = list(budget.allocations)
    if allocation_ids is None:
        targets = [a for a in rows if a.group != "savings" and a.zone_mode == "auto"]
    else:
        by_id = {a.id: a for a in rows}
        for allocation_id in allocation_ids:
            allocation = by_id.get(allocation_id)
            if allocation is None:
                raise NotFoundError(
                    f"Không có dòng phân bổ này trong ngân sách tháng {budget.period_month:%m/%Y}",
                    "allocation_not_found",
                )
            _ensure_tracked(allocation)
        targets = [by_id[i] for i in dict.fromkeys(allocation_ids) if by_id[i].zone_mode == "auto"]
    histories = load_histories(db, budget, targets)
    for allocation in targets:
        auto = calculate_auto_zone_from_history(
            allocation.planned_amount, histories[allocation.id], group=allocation.group
        )
        _apply(allocation, auto.thresholds)
    db.flush()
    db.commit()
    db.refresh(budget)
    return budget
