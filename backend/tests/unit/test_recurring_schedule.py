"""Lịch khoản định kỳ (phase-12 § 6 test case 4, 5) + icon lịch — hàm thuần."""

from datetime import date

import pytest

from app.services.recurring_schedule import (
    ScheduleRule,
    calendar_icon,
    day_in_month,
    due_status,
    first_on_or_after,
    is_occurrence,
    next_occurrence,
    occurrences,
)

MONTHLY_31 = ScheduleRule("monthly", day_of_month=31)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (date(2026, 1, 31), date(2026, 2, 28)),  # test case 4
        (date(2028, 1, 31), date(2028, 2, 29)),  # test case 4 — năm nhuận
        (date(2026, 2, 28), date(2026, 3, 31)),  # tháng sau về lại ngày 31
        (date(2026, 3, 31), date(2026, 4, 30)),
        (date(2026, 12, 31), date(2027, 1, 31)),  # qua năm
        (date(2026, 10, 22), date(2026, 10, 31)),  # cùng tháng
    ],
)
def test_monthly_day_31_uses_last_day_of_short_months(current, expected):
    assert next_occurrence(MONTHLY_31, current) == expected


def test_monthly_regular_day():
    rule = ScheduleRule("monthly", day_of_month=5)
    assert next_occurrence(rule, date(2026, 10, 5)) == date(2026, 11, 5)
    assert next_occurrence(rule, date(2026, 10, 4)) == date(2026, 10, 5)
    assert next_occurrence(rule, date(2026, 12, 20)) == date(2027, 1, 5)


def test_weekly_monday_from_wednesday():
    """Test case 5: weekly Thứ Hai, hôm nay 2026-10-07 (Thứ Tư) → 2026-10-12."""
    rule = ScheduleRule("weekly", day_of_week=1)
    assert next_occurrence(rule, date(2026, 10, 7)) == date(2026, 10, 12)
    # Đúng Thứ Hai → tuần sau (luôn sau ngày đang xét).
    assert next_occurrence(rule, date(2026, 10, 12)) == date(2026, 10, 19)
    assert next_occurrence(ScheduleRule("weekly", day_of_week=7), date(2026, 10, 7)) == date(
        2026, 10, 11
    )


def test_yearly_leap_day_falls_back_and_recovers():
    rule = ScheduleRule("yearly", day_of_month=29, month=2)
    days = [date(2028, 2, 29)]
    for _ in range(4):
        days.append(next_occurrence(rule, days[-1]))
    assert days == [
        date(2028, 2, 29),
        date(2029, 2, 28),
        date(2030, 2, 28),
        date(2031, 2, 28),
        date(2032, 2, 29),
    ]


def test_yearly_regular():
    rule = ScheduleRule("yearly", day_of_month=15, month=6)
    assert next_occurrence(rule, date(2026, 6, 14)) == date(2026, 6, 15)
    assert next_occurrence(rule, date(2026, 6, 15)) == date(2027, 6, 15)


def test_is_occurrence_and_first_on_or_after():
    assert is_occurrence(MONTHLY_31, date(2026, 2, 28))
    assert not is_occurrence(MONTHLY_31, date(2026, 2, 27))
    assert not is_occurrence(MONTHLY_31, date(2026, 3, 30))
    assert first_on_or_after(MONTHLY_31, date(2026, 4, 30)) == date(2026, 4, 30)
    assert is_occurrence(ScheduleRule("weekly", day_of_week=1), date(2026, 10, 12))
    assert not is_occurrence(ScheduleRule("weekly", day_of_week=1), date(2026, 10, 13))


def test_occurrences_in_window():
    rule = ScheduleRule("weekly", day_of_week=1)
    got = list(occurrences(rule, date(2026, 9, 28), date(2026, 10, 1), date(2026, 10, 20)))
    assert got == [date(2026, 10, 5), date(2026, 10, 12), date(2026, 10, 19)]
    monthly = list(
        occurrences(MONTHLY_31, date(2026, 10, 31), date(2026, 10, 1), date(2027, 1, 31))
    )
    assert monthly == [
        date(2026, 10, 31),
        date(2026, 11, 30),
        date(2026, 12, 31),
        date(2027, 1, 31),
    ]


def test_day_in_month_clamps():
    assert day_in_month(2026, 2, 30) == date(2026, 2, 28)
    assert day_in_month(2026, 7, 31) == date(2026, 7, 31)


@pytest.mark.parametrize(
    ("due", "status"),
    [
        (date(2026, 10, 21), "overdue"),
        (date(2026, 10, 22), "due_today"),
        (date(2026, 11, 5), "upcoming"),
        (date(2026, 11, 6), "later"),
    ],
)
def test_due_status(due, status):
    assert due_status(due, date(2026, 10, 22)) == status


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": "weekly"},
        {"frequency": "weekly", "day_of_week": 8},
        {"frequency": "monthly"},
        {"frequency": "monthly", "day_of_month": 32},
        {"frequency": "yearly", "day_of_month": 5},
        {"frequency": "daily", "day_of_month": 5},
    ],
)
def test_invalid_rules(kwargs):
    with pytest.raises(ValueError):
        ScheduleRule(**kwargs)


@pytest.mark.parametrize(
    ("direction", "slug", "name", "icon"),
    [
        ("income", "salary", "Lương", "💰"),
        ("income", "other_income", "Tiền nhà cho thuê", "💰"),
        ("expense", "housing", "Tiền nhà", "🏠"),
        ("expense", "other", "Thuê nhà", "🏠"),
        ("expense", "other", "Thanh toán thẻ tín dụng", "💳"),
        ("expense", "shopping", "Credit card VPBank", "💳"),
        ("expense", "utilities", "Điện nước", "📱"),
        ("expense", "other", "Internet FPT", "📱"),
        ("expense", "entertainment", "Netflix", "📱"),
        ("expense", "health", "Gym", "🔁"),
    ],
)
def test_calendar_icon(direction, slug, name, icon):
    assert calendar_icon(direction, slug, name) == icon
