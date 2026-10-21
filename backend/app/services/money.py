"""Tiền và kỳ thời gian — lõi deterministic (ADR-005, ADR-007).

Tiền là số nguyên đồng. Mọi phép làm tròn tiền dùng `round_vnd`.
"""

import calendar
from collections.abc import Sequence
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


def elapsed_days(month: date, today: date) -> int:
    """Số ngày đã qua của tháng chứa `month` tính tới `today` (tính cả hôm nay): tháng chưa tới
    → 0, tháng đã qua → đủ số ngày (pro-rata Phase 5, 9)."""
    start, end = month_range(month)
    if today < start:
        return 0
    if today > end:
        return end.day
    return today.day


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


def allocate_by_weights(total: int, weights: Sequence[int], step: int = 1) -> list[int]:
    """Chia `total` đồng theo tỉ lệ `weights`, mỗi phần là bội số của `step`; tổng luôn đúng
    bằng `total`.

    Phần lẻ tới `step` chia theo phần dư lớn nhất (bằng nhau → phần đứng trước); phần lẻ dưới
    `step` (khi `total` không chia hết cho `step`) cộng vào phần có trọng số lớn nhất.

    >>> allocate_by_weights(25_000_000, [50, 30, 20], 1000)
    [12500000, 7500000, 5000000]
    >>> allocate_by_weights(10_000, [1, 1, 1], 1000)
    [4000, 3000, 3000]
    """
    if total < 0:
        raise ValueError("total phải >= 0")
    if step <= 0:
        raise ValueError("step phải > 0")
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError("weights phải không âm và có tổng > 0")
    weight_sum = sum(weights)
    units, sub_step = divmod(total, step)
    exact = [Fraction(units * w, weight_sum) for w in weights]
    shares = [int(x) for x in exact]
    leftover = units - sum(shares)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-(exact[i] - shares[i]), i))
    for i in by_remainder[:leftover]:
        shares[i] += 1
    amounts = [s * step for s in shares]
    amounts[max(range(len(weights)), key=lambda i: (weights[i], -i))] += sub_step
    return amounts


def format_vnd(amount: int) -> str:
    """`2000000` → `2.000.000 ₫` (dùng trong thông báo lỗi; frontend tự format số)."""
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,}".replace(",", ".") + " ₫"
