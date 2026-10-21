"""Toán goal / PYF thuần (phase-11 § 4.2, § 6 test case 1–4) — không cần DB, không AI."""

from datetime import date

import pytest

from app.services.goal_service import (
    ceil_to_step,
    compute_progress,
    months_remaining,
    plan_allocation,
    progress_pct,
    suggested_monthly_saving,
)

TODAY = date(2026, 10, 22)


@pytest.mark.parametrize(
    ("today", "deadline", "expected"),
    [
        (TODAY, date(2027, 3, 22), 5),  # tháng 10, 11, 12, 1, 2
        (TODAY, date(2027, 3, 1), 5),  # ngày trong tháng đến hạn không đổi kết quả
        (TODAY, date(2027, 3, 31), 5),
        (TODAY, date(2026, 11, 1), 1),
        (TODAY, date(2026, 12, 31), 2),
        (TODAY, date(2026, 10, 31), 1),  # đến hạn ngay trong tháng → tối thiểu 1
        (TODAY, TODAY, 1),  # hạn là hôm nay → chưa quá hạn
        (TODAY, date(2026, 10, 21), 0),  # quá hạn
        (date(2026, 10, 31), date(2026, 11, 1), 1),  # ranh giới cuối tháng
        (date(2026, 11, 1), date(2026, 11, 30), 1),
        (date(2026, 12, 31), date(2027, 1, 1), 1),  # qua năm
        (date(2026, 1, 1), date(2027, 1, 1), 12),
    ],
)
def test_months_remaining(today, deadline, expected):
    assert months_remaining(today, deadline) == expected


def test_ceil_to_step():
    assert ceil_to_step(0) == 0
    assert ceil_to_step(1) == 100_000
    assert ceil_to_step(4_400_000) == 4_400_000
    assert ceil_to_step(4_400_001) == 4_500_000
    assert ceil_to_step(1_234, 1_000) == 2_000
    with pytest.raises(ValueError):
        ceil_to_step(1, 0)


@pytest.mark.parametrize(
    ("remaining", "months", "expected"),
    [
        (22_000_000, 5, 4_400_000),  # test case 1
        (10_000_000, 3, 3_400_000),  # 3.333.333 → làm tròn lên 100.000
        (150_000, 1, 150_000),  # không vượt phần còn thiếu
        (150_000, 12, 100_000),
        (0, 5, 0),  # test case 2
        (-5, 5, 0),
        (2_000_000, 0, 2_000_000),  # quá hạn → toàn bộ còn thiếu
    ],
)
def test_suggested_monthly_saving(remaining, months, expected):
    assert suggested_monthly_saving(remaining, months) == expected


def test_progress_pct():
    assert progress_pct(8_000_000, 30_000_000) == 26.7
    assert progress_pct(0, 30_000_000) == 0.0
    assert progress_pct(30_000_000, 30_000_000) == 100.0
    assert progress_pct(40_000_000, 30_000_000) == 100.0
    assert progress_pct(1, 0) == 0.0


def test_case_1_laptop_goal():
    p = compute_progress(30_000_000, 8_000_000, date(2027, 3, 22), TODAY)
    assert (p.remaining, p.months_remaining, p.suggested_monthly_saving) == (
        22_000_000,
        5,
        4_400_000,
    )
    assert p.on_track and not p.overdue
    assert p.current + p.suggested_monthly_saving * p.months_remaining >= 30_000_000


def test_case_2_reached_goal():
    p = compute_progress(10_000_000, 10_000_000, date(2027, 3, 22), TODAY)
    assert (p.remaining, p.suggested_monthly_saving, p.progress_pct) == (0, 0, 100.0)
    assert p.on_track and not p.overdue
    # Đã đạt thì quá hạn cũng không "behind".
    late = compute_progress(10_000_000, 10_000_000, date(2026, 1, 1), TODAY)
    assert late.on_track and not late.overdue and late.months_remaining == 0


def test_overdue_goal_is_behind():
    p = compute_progress(10_000_000, 4_000_000, date(2026, 9, 30), TODAY)
    assert p.months_remaining == 0 and p.overdue and not p.on_track
    assert p.suggested_monthly_saving == 6_000_000


def test_case_3_priority_allocation():
    amounts, savings = plan_allocation(
        25_000_000, [(4_400_000, 22_000_000), (2_000_000, 12_000_000)], 5_000_000
    )
    assert amounts == [4_400_000, 2_000_000] and savings == 5_000_000
    assert 25_000_000 - sum(amounts) - savings == 13_600_000


def test_case_4_income_runs_out():
    amounts, savings = plan_allocation(5_000_000, [(4_400_000, 22_000_000)], 5_000_000)
    assert amounts == [4_400_000] and savings == 600_000
    assert 5_000_000 - sum(amounts) - savings == 0


def test_allocation_caps_and_order():
    # Goal ưu tiên 1 lấy trước; goal sau nhận phần còn lại; không vượt phần còn thiếu.
    amounts, savings = plan_allocation(
        3_000_000, [(2_500_000, 2_500_000), (2_000_000, 500_000), (1_000_000, 1_000_000)], None
    )
    assert amounts == [2_500_000, 500_000, 0] and savings == 0
    assert plan_allocation(1_000_000, [], 5_000_000) == ([], 1_000_000)
    assert plan_allocation(1_000_000, [], None) == ([], 0)
