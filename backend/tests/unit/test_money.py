from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from app.services.money import add_months, month_range, round_vnd, week_range


@pytest.mark.parametrize(
    ("value", "step", "expected"),
    [
        (55_000, 1, 55_000),
        (1_234_567, 1000, 1_235_000),
        (1_234_499, 1000, 1_234_000),
        (1_500, 1000, 2_000),  # nửa làm tròn lên, không phải banker's rounding
        (2_500, 1000, 3_000),
        (Fraction(10, 3), 1, 3),
        (Fraction(25_000_000 * 3, 10), 1000, 7_500_000),
        (Decimal("1234.5"), 1, 1235),
        (0.1 + 0.2, 1, 0),
        (2.5, 1, 3),
        (-1_500, 1000, -2_000),
    ],
)
def test_round_vnd(value, step, expected):
    assert round_vnd(value, step) == expected
    assert isinstance(round_vnd(value, step), int)


def test_round_vnd_rejects_bad_step():
    with pytest.raises(ValueError):
        round_vnd(1000, 0)


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 10, 7), (date(2026, 10, 1), date(2026, 10, 31))),
        (date(2026, 9, 30), (date(2026, 9, 1), date(2026, 9, 30))),
        (date(2028, 2, 10), (date(2028, 2, 1), date(2028, 2, 29))),
        (date(2026, 2, 1), (date(2026, 2, 1), date(2026, 2, 28))),
        (date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),
    ],
)
def test_month_range(d, expected):
    assert month_range(d) == expected


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 10, 7), (date(2026, 10, 5), date(2026, 10, 11))),  # test case #7
        (date(2026, 10, 5), (date(2026, 10, 5), date(2026, 10, 11))),  # Thứ Hai
        (date(2026, 10, 11), (date(2026, 10, 5), date(2026, 10, 11))),  # Chủ Nhật
        (date(2026, 1, 1), (date(2025, 12, 29), date(2026, 1, 4))),  # qua năm
    ],
)
def test_week_range_starts_monday(d, expected):
    start, end = week_range(d)
    assert (start, end) == expected
    assert start.isoweekday() == 1


@pytest.mark.parametrize(
    ("d", "months", "expected"),
    [
        (date(2026, 10, 8), -3, date(2026, 7, 8)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 11, 15), 2, date(2027, 1, 15)),
        (date(2026, 3, 31), -13, date(2025, 2, 28)),
    ],
)
def test_add_months(d, months, expected):
    assert add_months(d, months) == expected
