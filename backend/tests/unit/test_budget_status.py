"""Tính toán Budget vs Actual thuần (Phase 5) — không cần DB / OpenAI."""

import uuid
from datetime import date
from fractions import Fraction
from types import SimpleNamespace

import pytest

from app.services.analytics_service import (
    effective_scope,
    evaluate_allocation,
    expected_to_date,
    month_progress,
    pace_status,
    scope_actual,
    to_float,
    top_contributor_share,
    tracking_status,
    used_percent,
)
from app.services.budget_service import AllocationScope

OCT = date(2026, 10, 1)


# ---------- tiến độ tháng ----------


def test_month_progress_mid_month():
    progress = month_progress(OCT, date(2026, 10, 15))
    assert (progress.elapsed_days, progress.days_in_month) == (15, 31)
    assert progress.date_from == OCT
    assert progress.date_to == date(2026, 10, 31)
    assert progress.ratio == Fraction(15, 31)
    assert progress.to_read().month_progress == 0.4839


@pytest.mark.parametrize(
    ("today", "elapsed"),
    [
        (date(2026, 9, 30), 0),  # tháng chưa tới
        (date(2026, 10, 1), 1),
        (date(2026, 10, 31), 31),
        (date(2026, 12, 5), 31),  # tháng đã qua
    ],
)
def test_month_progress_bounds(today, elapsed):
    assert month_progress(OCT, today).elapsed_days == elapsed


def test_month_progress_february_leap_year():
    progress = month_progress(date(2028, 2, 1), date(2028, 2, 10))
    assert progress.days_in_month == 29
    assert progress.ratio == Fraction(10, 29)


# ---------- used %, expected to date, pace ----------


def test_used_percent():
    assert used_percent(4_500_000, 4_000_000) == 112.5
    assert used_percent(700_000, 1_000_000) == 70.0
    assert used_percent(1, 3) == 33.3
    assert used_percent(2, 3) == 66.7
    assert used_percent(0, 1_000_000) == 0.0
    assert used_percent(500_000, 0) is None


def test_to_float_rounds_half_up():
    assert to_float(Fraction(1, 8), 2) == 0.13
    assert to_float(Fraction(15, 31), 4) == 0.4839


def test_expected_to_date_pro_rata():
    """Test case 5: planned 4.000.000, ngày 15/31 → ~1.935.484."""
    assert expected_to_date(4_000_000, Fraction(15, 31)) == 1_935_484
    assert expected_to_date(4_000_000, Fraction(0)) == 0
    assert expected_to_date(4_000_000, Fraction(1)) == 4_000_000


def test_pace_status_with_ten_point_tolerance():
    progress = Fraction(15, 31)  # ~48,4%
    assert pace_status(3_000_000, 4_000_000, progress) == "ahead"  # 75%
    assert pace_status(2_000_000, 4_000_000, progress) == "on_track"  # 50%
    assert pace_status(1_000_000, 4_000_000, progress) == "under"  # 25%
    # Đúng biên 10 điểm % vẫn là on_track.
    assert pace_status(60, 100, Fraction(1, 2)) == "on_track"
    assert pace_status(40, 100, Fraction(1, 2)) == "on_track"
    assert pace_status(61, 100, Fraction(1, 2)) == "ahead"
    assert pace_status(39, 100, Fraction(1, 2)) == "under"
    assert pace_status(100, 0, Fraction(1, 2)) is None


def test_tracking_status():
    assert tracking_status("savings", 0, 5_000_000, None) == "not_tracked"
    assert tracking_status("wants", 3_200_000, 2_000_000, "ahead") == "over_budget"
    assert tracking_status("essential", 3_000_000, 4_000_000, "ahead") == "ahead_of_pace"
    assert tracking_status("essential", 5_000_000, 5_000_000, "on_track") == "on_track"
    assert tracking_status("essential", 100, 0, None) == "over_budget"


def test_evaluate_allocation_under_budget():
    """Test case 3: transport planned 1.000.000, actual 700.000, tháng đã kết thúc."""
    metrics = evaluate_allocation("essential", 1_000_000, 700_000, Fraction(1))
    assert metrics.variance == -300_000
    assert metrics.remaining == 300_000
    assert metrics.used_percent == 70.0
    assert metrics.overspend == 0
    assert metrics.pace_status == "under"
    assert metrics.status == "on_track"


def test_evaluate_allocation_over_budget():
    """Test case 1: food planned 4.000.000, actual 4.500.000."""
    metrics = evaluate_allocation("essential", 4_000_000, 4_500_000, Fraction(1))
    assert (metrics.variance, metrics.remaining) == (500_000, -500_000)
    assert metrics.used_percent == 112.5
    assert metrics.overspend == 500_000
    assert metrics.status == "over_budget"


def test_evaluate_allocation_savings_is_not_tracked():
    metrics = evaluate_allocation("savings", 5_000_000, 0, Fraction(15, 31))
    assert metrics.actual == 0
    assert metrics.pace_status is None
    assert metrics.status == "not_tracked"


# ---------- top contributor ----------


def test_top_contributor_share():
    """Test case 2: overspend 1.200.000, giao dịch 900.000 → 75%."""
    assert top_contributor_share(900_000, 1_200_000) == Fraction(3, 4)
    assert top_contributor_share(720_000, 1_200_000) == Fraction(3, 5)  # đúng 60%
    assert top_contributor_share(719_000, 1_200_000) is None
    assert top_contributor_share(4_385_000, 500_000) == 1  # lớn hơn phần vượt → tối đa 1
    assert top_contributor_share(900_000, 0) is None


# ---------- phạm vi ----------


def test_scope_actual_by_category_and_spending_type():
    food, shopping, housing = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        (food, "essential", 4_000_000, 20),
        (food, "non_essential", 500_000, 5),
        (shopping, "non_essential", 3_200_000, 5),
        (housing, "essential", 5_000_000, 1),
    ]
    assert scope_actual(AllocationScope("category", category_ids=frozenset({food})), rows) == (
        4_500_000,
        25,
    )
    jar = AllocationScope("jar", category_ids=frozenset({food, housing}))
    assert scope_actual(jar, rows) == (9_500_000, 26)
    wants = AllocationScope("group", spending_types=frozenset({"non_essential"}))
    assert scope_actual(wants, rows) == (3_700_000, 10)
    assert scope_actual(AllocationScope("group"), rows) == (0, 0)


def test_effective_scope_savings_matches_nothing():
    food = uuid.uuid4()
    saving_row = SimpleNamespace(group="savings", category_id=food, jar_name=None)
    assert effective_scope("fifty_thirty_twenty", saving_row, {}) == AllocationScope("category")
    group_row = SimpleNamespace(group="savings", category_id=None, jar_name="savings")
    assert effective_scope("pyf", group_row, {}) == AllocationScope("group")
    essential = SimpleNamespace(group="essential", category_id=None, jar_name="Essential")
    assert effective_scope("envelope", essential, {"Essential": [food]}) == AllocationScope(
        "jar", category_ids=frozenset({food})
    )
