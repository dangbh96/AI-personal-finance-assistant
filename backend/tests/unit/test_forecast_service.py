"""Dự báo dòng tiền (phase-12 § 6 test case 6, 7) + lịch để dành mục tiêu — hàm thuần, số VND
nguyên cụ thể."""

from datetime import date, timedelta

import pytest

from app.services.forecast_service import (
    CashflowEvent,
    GoalPlanInput,
    goal_saving_schedule,
    project_balance,
    variable_average,
)

OCT_1 = date(2026, 10, 1)


def _event(day: int, amount: int, direction="expense", kind="recurring", label="x"):
    return CashflowEvent(
        on=date(2026, 10, day),
        kind=kind,
        direction=direction,
        amount=amount,
        label=label,
        icon="🔁",
    )


def test_case_6_forecast_day_10():
    """12.000.000 + lương 25.000.000 (ngày 5) − nhà 5.000.000 (ngày 1) − mục tiêu 4.400.000
    (ngày 10) − 200.000 × 10 ngày = 25.600.000."""
    events = [
        _event(1, 5_000_000, label="Tiền nhà"),
        _event(5, 25_000_000, direction="income", label="Lương"),
        _event(10, 4_400_000, kind="goal_saving", label="Để dành"),
    ]
    projection = project_balance(12_000_000, OCT_1, 30, events, 200_000, 1_000_000)
    by_day = {p.on: p for p in projection.days}
    day10 = by_day[date(2026, 10, 10)]
    assert day10.projected_balance == 25_600_000
    assert isinstance(day10.projected_balance, int)
    assert day10.delta_goal_saving == 4_400_000
    assert by_day[OCT_1].projected_balance == 12_000_000 - 5_000_000 - 200_000
    assert by_day[date(2026, 10, 5)].delta_income == 25_000_000
    assert by_day[date(2026, 10, 5)].projected_balance == 31_000_000
    assert len(projection.days) == 30
    assert projection.end_balance == 12_000_000 + 25_000_000 - 5_000_000 - 4_400_000 - 6_000_000
    assert projection.low_balance_warning_day is None
    assert projection.min_balance == 6_200_000
    assert projection.min_balance_day == date(2026, 10, 4)


def test_case_7_low_balance_warning_day():
    """Ngưỡng 1.000.000; số dư dự báo ngày 25 = 800.000 → cảnh báo 2026-10-25."""
    events = [_event(1, 5_000_000), _event(5, 300_000)]
    projection = project_balance(12_000_000, OCT_1, 30, events, 236_000, 1_000_000)
    by_day = {p.on: p.projected_balance for p in projection.days}
    assert by_day[date(2026, 10, 24)] == 1_036_000
    assert by_day[date(2026, 10, 25)] == 800_000
    assert projection.low_balance_warning_day == date(2026, 10, 25)
    assert projection.min_balance_day == date(2026, 10, 30)


def test_warning_exactly_at_threshold_is_not_low():
    projection = project_balance(1_000_000, OCT_1, 3, [], 0, 1_000_000)
    assert projection.low_balance_warning_day is None


def test_actual_transactions_by_day_are_included():
    actual = {date(2026, 10, 2): {"income": 1_000_000, "expense": 300_000}}
    projection = project_balance(0, OCT_1, 3, [], 100_000, 0, actual)
    assert [p.projected_balance for p in projection.days] == [-100_000, 500_000, 400_000]
    assert projection.days[1].delta_income == 1_000_000
    assert projection.days[1].delta_expense == 300_000
    assert projection.low_balance_warning_day == OCT_1


def test_project_balance_requires_days():
    with pytest.raises(ValueError):
        project_balance(0, OCT_1, 0, [], 0, 0)


def _goal(name="Laptop", target=30_000_000, current=8_000_000, in_month=0, deadline=None):
    return GoalPlanInput(
        name=name,
        target=target,
        current=current,
        contributed_in_start_month=in_month,
        deadline=deadline or date(2027, 3, 22),
    )


def test_goal_schedule_monthly_on_day_10():
    schedule = goal_saving_schedule([_goal()], OCT_1, OCT_1 + timedelta(days=59), 10)
    assert schedule == [
        (date(2026, 10, 10), 4_400_000, ["Laptop"]),
        (date(2026, 11, 10), 4_400_000, ["Laptop"]),
    ]


def test_goal_schedule_skips_day_already_passed():
    schedule = goal_saving_schedule([_goal()], date(2026, 10, 22), date(2026, 12, 20), 10)
    assert [(d, a) for d, a, _ in schedule] == [
        (date(2026, 11, 10), 4_400_000),
        (date(2026, 12, 10), 4_400_000),
    ]


def test_goal_schedule_subtracts_contributions_this_month():
    # Đã góp đủ 4.400.000 trong tháng 10 → tháng 10 không còn khoản nào.
    full = goal_saving_schedule(
        [_goal(current=12_400_000, in_month=4_400_000)], OCT_1, date(2026, 11, 30), 10
    )
    assert [(d, a) for d, a, _ in full] == [(date(2026, 11, 10), 4_400_000)]
    # Góp 1.400.000 → còn 3.000.000.
    partial = goal_saving_schedule(
        [_goal(current=9_400_000, in_month=1_400_000)], OCT_1, date(2026, 10, 31), 10
    )
    assert partial == [(date(2026, 10, 10), 3_000_000, ["Laptop"])]


def test_goal_schedule_stops_before_deadline_month_and_caps_remaining():
    goal = _goal(target=10_000_000, current=0, deadline=date(2026, 12, 15))
    schedule = goal_saving_schedule([goal], OCT_1, date(2027, 1, 31), 10)
    assert [(d, a) for d, a, _ in schedule] == [
        (date(2026, 10, 10), 5_000_000),
        (date(2026, 11, 10), 5_000_000),
    ]
    small = _goal(target=1_000_000, current=0, deadline=date(2027, 12, 1))
    capped = goal_saving_schedule([small], OCT_1, date(2027, 11, 30), 10)
    assert sum(a for _, a, _ in capped) == 1_000_000
    assert all(a == 100_000 for _, a, _ in capped)


def test_goal_schedule_overdue_goal_only_current_month():
    goal = _goal(target=5_000_000, current=2_000_000, deadline=date(2026, 9, 30))
    schedule = goal_saving_schedule([goal], OCT_1, date(2026, 12, 31), 10)
    assert schedule == [(date(2026, 10, 10), 3_000_000, ["Laptop"])]


def test_goal_schedule_sums_goals_and_clamps_day():
    goals = [_goal(), _goal(name="Du lịch", target=6_000_000, current=0)]
    schedule = goal_saving_schedule(goals, date(2027, 2, 1), date(2027, 2, 28), 31)
    # Tháng 2 → ngày 28; Laptop còn 1 tháng trước hạn 03/2027 → 22.000.000, Du lịch 6.000.000.
    assert schedule == [(date(2027, 2, 28), 28_000_000, ["Laptop", "Du lịch"])]


def test_goal_schedule_without_goals():
    assert goal_saving_schedule([], OCT_1, date(2026, 12, 31), 10) == []


@pytest.mark.parametrize(
    ("total", "days", "expected"),
    [
        (6_000_000, 30, 200_000),
        (1_000, 7, 143),  # 142,857… → 143
        (5_000_000, 6, 0),  # < 7 ngày lịch sử → 0
        (0, 30, 0),
    ],
)
def test_variable_average(total, days, expected):
    assert variable_average(total, days) == expected
