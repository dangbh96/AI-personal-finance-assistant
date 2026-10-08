"""Tiền và kỳ thời gian — lõi deterministic (ADR-005, ADR-007).

Tiền là số nguyên đồng. Mọi phép làm tròn tiền dùng `round_vnd`.
"""

import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

Number = int | float | Decimal | Fraction


def round_vnd(x: Number, step: int = 1) -> int:
    """Làm tròn `x` (đồng) tới bội số gần nhất của `step`, nửa làm tròn ra xa 0.

    >>> round_vnd(1_234_567, 1000)
    1235000
    >>> round_vnd(Fraction(10, 3))
    3
    """
    if step <= 0:
        raise ValueError("step phải > 0")
    if isinstance(x, float):
        value = Decimal(repr(x))
    elif isinstance(x, Fraction):
        value = Decimal(x.numerator) / Decimal(x.denominator)
    else:
        value = Decimal(x)
    units = (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(units) * step


def month_range(d: date) -> tuple[date, date]:
    """Ngày đầu và ngày cuối (bao gồm) của tháng chứa `d`."""
    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=1), d.replace(day=last_day)


def week_range(d: date) -> tuple[date, date]:
    """Thứ Hai và Chủ Nhật (bao gồm) của tuần chứa `d` — tuần bắt đầu Thứ Hai."""
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def add_months(d: date, months: int) -> date:
    """Cộng/trừ tháng, giữ ngày nếu được, nếu không thì kẹp về ngày cuối tháng."""
    month_index = d.year * 12 + d.month - 1 + months
    year, month = divmod(month_index, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(d.day, last_day))
