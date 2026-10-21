"""Flexible budget zones (phase-09 § 6, budget-adjustment.md § 2) — hàm thuần, không DB/AI.

Độ lệch chuẩn là population std (chia n); ngưỡng làm tròn tới đồng (half-up).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from app.core.errors import DomainError
from app.services import advisor_rules, zone_service
from app.services.advisor_rules import AdviceInput, MonthActual, ScopeTransaction
from app.services.budget_service import AllocationScope
from app.services.money import elapsed_days
from app.services.zone_service import HistoryMonth, ZoneThresholds

OCT = date(2026, 10, 1)


@dataclass
class _Allocation:
    planned_amount: int
    comfort_low: int | None = None
    comfort_high: int | None = None
    warning_threshold: int | None = None
    zone_mode: str = "manual"
    group: str = "essential"


def _history(values: list[int | None], irregular: dict[int, int] | None = None):
    """Các tháng trước tháng 10 (cũ nhất trước); `None` = tháng không có giao dịch nào."""
    irregular = irregular or {}
    months = zone_service.history_months(OCT)[-len(values) :]
    return [
        HistoryMonth(m, v or 0, irregular.get(i, 0), 0 if v is None and i not in irregular else 5)
        for i, (m, v) in enumerate(zip(months, values, strict=True))
    ]


# ---------- auto: lịch sử >= 3 tháng (test case 1, 2) ----------


def test_case_1_auto_food_from_history():
    auto = zone_service.calculate_auto_zone_from_history(
        4_000_000, _history([3_800_000, 4_200_000, 4_000_000]), group="essential"
    )
    assert auto.basis == "history"
    assert auto.mean == 4_000_000
    assert round(auto.std, 3) == Decimal("163299.316")
    assert auto.thresholds == ZoneThresholds(
        comfort_low=3_500_000, comfort_high=4_081_650, warning_threshold=4_400_000
    )


def test_case_2_auto_shopping_excludes_irregular_laptop():
    history = _history([1_800_000, 2_100_000, 2_000_000], irregular={0: 6_500_000})
    assert history[0].irregular == 6_500_000
    auto = zone_service.calculate_auto_zone_from_history(2_000_000, history, group="wants")
    assert auto.basis == "history"
    assert round(auto.mean) == 1_966_667
    assert round(auto.std) == 124_722
    assert auto.thresholds == ZoneThresholds(
        comfort_low=1_750_000, comfort_high=2_029_028, warning_threshold=2_200_000
    )


def test_scope_history_splits_irregular_and_counts_scope_only():
    food, shopping = uuid.uuid4(), uuid.uuid4()
    scope = AllocationScope("category", category_ids=frozenset({shopping}))
    rows = {
        date(2026, 7, 1): [
            (shopping, "non_essential", 1_800_000, 3),
            (shopping, "irregular", 6_500_000, 1),
            (food, "essential", 4_000_000, 20),
        ],
        date(2026, 8, 1): [(food, "essential", 4_000_000, 20)],
    }
    result = zone_service.scope_history(scope, rows)
    assert [(h.actual, h.irregular, h.transaction_count, h.has_data) for h in result] == [
        (1_800_000, 6_500_000, 4, True),
        (0, 0, 0, False),
    ]


def test_group_scope_matches_spending_type():
    scope = AllocationScope("group", spending_types=frozenset({"non_essential"}))
    cid = uuid.uuid4()
    rows = {OCT: [(cid, "non_essential", 500_000, 2), (cid, "essential", 900_000, 3)]}
    assert zone_service.scope_history(scope, rows)[0].actual == 500_000


def test_auto_uses_at_most_six_most_recent_months_with_data():
    values = [1_000_000, 2_000_000, 2_000_000, 2_000_000, 2_000_000, 2_000_000]
    auto = zone_service.calculate_auto_zone_from_history(2_000_000, _history(values), group="wants")
    assert auto.mean == Fraction(11_000_000, 6)
    assert len(auto.used_months) == 6
    # Bỏ tháng trống: 3 tháng có dữ liệu trong 6 tháng là đủ.
    sparse = _history([None, 3_800_000, None, 4_200_000, None, 4_000_000])
    auto = zone_service.calculate_auto_zone_from_history(4_000_000, sparse, group="essential")
    assert auto.basis == "history"
    assert auto.thresholds.comfort_high == 4_081_650
    assert len(auto.used_months) == 3


def test_auto_comfort_high_never_below_planned():
    auto = zone_service.calculate_auto_zone_from_history(
        5_000_000, _history([3_000_000, 3_000_000, 3_000_000]), group="essential"
    )
    assert auto.thresholds == ZoneThresholds(4_375_000, 5_000_000, 5_500_000)


def test_auto_is_idempotent():
    history = _history([3_800_000, 4_200_000, 4_000_000])
    first = zone_service.calculate_auto_zone_from_history(4_000_000, history, group="essential")
    second = zone_service.calculate_auto_zone_from_history(4_000_000, history, group="essential")
    assert first == second


# ---------- auto: thiếu dữ liệu (test case 3) ----------


def test_case_3_fallback_when_history_missing():
    auto = zone_service.calculate_auto_zone_from_history(
        1_000_000, _history([None, 900_000, 1_100_000]), group="essential"
    )
    assert (auto.basis, auto.fallback_reason) == ("fallback", "insufficient_history")
    assert auto.thresholds == ZoneThresholds(875_000, 1_125_000, 1_250_000)


def test_fallback_rounds_to_nearest_dong():
    # 0.875 × 1.000.003 = 875.002,625 · 1.125 × = 1.125.003,375 · 1.25 × = 1.250.003,75
    assert zone_service.fallback_thresholds(1_000_003) == ZoneThresholds(
        875_003, 1_125_003, 1_250_004
    )
    # .5 làm tròn lên: 0.875 × 4 = 3,5 → 4
    assert zone_service.fallback_thresholds(4).comfort_low == 4


def test_irregular_group_always_uses_fallback():
    auto = zone_service.calculate_auto_zone_from_history(
        2_000_000, _history([0, 0, 0], irregular={0: 1, 1: 1, 2: 1}), group="irregular"
    )
    assert (auto.basis, auto.fallback_reason) == ("fallback", "irregular_group")
    assert auto.thresholds == ZoneThresholds(1_750_000, 2_250_000, 2_500_000)


# ---------- manual + zone (test case 4, 5, 6) ----------


def test_case_4_manual_entertainment_attention():
    thresholds = zone_service.validate_manual_thresholds(800_000, 1_200_000, 1_500_000)
    assert zone_service.zone_for(1_300_000, thresholds) == "attention"


def test_case_5_manual_invalid_low_above_high():
    with pytest.raises(DomainError) as exc:
        zone_service.validate_manual_thresholds(1_300_000, 1_200_000, 1_500_000)
    assert exc.value.code == "invalid_zone_thresholds"


def test_manual_high_above_warning_and_missing_values():
    with pytest.raises(DomainError) as exc:
        zone_service.validate_manual_thresholds(800_000, 1_600_000, 1_500_000)
    assert exc.value.code == "invalid_zone_thresholds"
    with pytest.raises(DomainError) as exc:
        zone_service.validate_manual_thresholds(800_000, None, 1_500_000)
    assert exc.value.code == "zone_thresholds_required"
    # Bằng nhau vẫn hợp lệ.
    assert zone_service.validate_manual_thresholds(1, 1, 1) == ZoneThresholds(1, 1, 1)


def test_case_6_food_review_needed():
    thresholds = ZoneThresholds(3_500_000, 4_100_000, 4_200_000)
    assert zone_service.zone_for(4_250_000, thresholds) == "review_needed"


@pytest.mark.parametrize(
    ("actual", "zone"),
    [
        (4_100_000, "normal"),
        (4_100_001, "attention"),
        (4_200_000, "attention"),
        (4_200_001, "review_needed"),
    ],
)
def test_zone_boundaries(actual, zone):
    assert zone_service.zone_for(actual, ZoneThresholds(3_500_000, 4_100_000, 4_200_000)) == zone


# ---------- pro-rata (test case 7) ----------


def test_case_7_early_warning_mid_month():
    allocation = _Allocation(4_000_000, 3_500_000, 4_500_000, 5_000_000)
    reading = zone_service.get_zone_status(3_200_000, allocation, date(2026, 10, 15), OCT)
    assert elapsed_days(OCT, date(2026, 10, 15)) == 15
    assert reading.expected_to_date == 1_935_484
    assert reading.early_warning is True
    assert reading.early_warning_message == "Đã dùng 80% ngân sách khi mới qua 48,4% tháng"
    # Không đổi zone chính khi vẫn dưới comfort_high.
    assert reading.zone == "normal"


def test_pro_rata_within_tolerance_and_outside_running_month():
    # 55% đã dùng khi qua 48,4% tháng: chênh < 10 điểm % → không cảnh báo.
    assert zone_service.pro_rata(2_200_000, 4_000_000, 15, 31)[1] is None
    # Tháng đã qua / chưa tới / planned = 0 → không cảnh báo sớm.
    assert zone_service.pro_rata(4_000_000, 4_000_000, 31, 31)[1] is None
    assert zone_service.pro_rata(4_000_000, 4_000_000, 0, 31)[1] is None
    assert zone_service.pro_rata(100_000, 0, 10, 31) == (0, None)
    # Đúng biên 10 điểm % vẫn không cảnh báo: 60% khi qua 50% tháng (15/30).
    assert zone_service.pro_rata(600_000, 1_000_000, 15, 30)[1] is None
    assert zone_service.pro_rata(600_001, 1_000_000, 15, 30)[1] is not None


def test_early_warning_kept_when_zone_already_attention():
    allocation = _Allocation(1_000_000, 875_000, 1_125_000, 1_250_000)
    reading = zone_service.get_zone_status(1_200_000, allocation, date(2026, 10, 10), OCT)
    assert (reading.zone, reading.early_warning) == ("attention", True)


def test_uncalculated_auto_has_no_zone_but_still_pro_rata():
    allocation = _Allocation(4_000_000, zone_mode="auto")
    reading = zone_service.get_zone_status(3_200_000, allocation, date(2026, 10, 15), OCT)
    assert reading.zone is None
    assert reading.early_warning is True
    zone = zone_service.allocation_zone(allocation, 3_200_000, 15, 31)
    assert zone is not None and (zone.calculated, zone.zone) == (False, None)


def test_savings_has_no_zone():
    allocation = _Allocation(5_000_000, group="savings", zone_mode="auto")
    assert zone_service.allocation_zone(allocation, 0, 15, 31) is None
    assert zone_service.zone_evidence(allocation, 0, 15, 31) is None


def test_auto_detail_reports_stale_cache():
    history = _history([3_800_000, 4_200_000, 4_000_000])
    fresh = _Allocation(4_000_000, 3_500_000, 4_081_650, 4_400_000, zone_mode="auto")
    detail = zone_service.auto_detail(fresh, history)
    assert (detail.basis, detail.history_months, detail.mean, detail.std) == (
        "history",
        3,
        4_000_000,
        163_299,
    )
    assert detail.stale is False
    assert [h.used for h in detail.history] == [True, True, True]
    old = _Allocation(4_000_000, 3_500_000, 4_500_000, 5_000_000, zone_mode="auto")
    assert zone_service.auto_detail(old, history).stale is True


# ---------- advisor dùng comfort_high (test case 8) ----------


def test_case_8_advisor_uses_comfort_high():
    allocation = _Allocation(4_000_000, 3_500_000, 4_500_000, 5_000_000)
    zone = zone_service.zone_evidence(allocation, 4_300_000, 31, 31)
    assert zone is not None and (zone.zone, zone.comfort_high) == ("normal", 4_500_000)
    inp = AdviceInput(
        label="Ăn uống",
        group="essential",
        category_slug="food",
        month=OCT,
        as_of=date(2026, 10, 31),
        month_complete=True,
        planned=4_000_000,
        actual=4_300_000,
        comfort_high=allocation.comfort_high,
        transactions=[
            ScopeTransaction(
                uuid.uuid4(), date(2026, 10, 1 + i), "Đi chợ", 215_000, "Ăn uống", "essential"
            )
            for i in range(20)
        ],
        history=[
            MonthActual(date(2026, 8, 1), 4_400_000, 20),
            MonthActual(date(2026, 9, 1), 4_600_000, 20),
            MonthActual(OCT, 4_300_000, 20),
        ],
        zone=zone,
    )
    result = advisor_rules.evaluate(inp)
    assert result.verdict == "on_track"
    assert (result.evidence.comfort_high_used, result.evidence.threshold_amount) == (
        True,
        4_500_000,
    )
    assert result.evidence.zone == zone
    # Không có vùng → so với planned như Phase 8.
    no_zone = advisor_rules.evaluate(
        AdviceInput(**{**inp.__dict__, "comfort_high": None, "zone": None})
    )
    assert no_zone.verdict != "on_track"
