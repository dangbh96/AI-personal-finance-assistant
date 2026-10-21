"""Phát hiện khoản định kỳ (phase-12 § 6 test case 1–3) — hàm thuần, không DB."""

import uuid
from datetime import date, timedelta
from fractions import Fraction

from app.services.recurring_detection import (
    HistoryItem,
    amount_clusters,
    amount_consistency,
    classify_interval,
    detect_patterns,
    infer_day_of_month,
    median_amount,
    within_tolerance,
)

HOUSING = uuid.UUID("00000000-0000-0000-0000-000000000001")
UTILITIES = uuid.UUID("00000000-0000-0000-0000-000000000002")
FOOD = uuid.UUID("00000000-0000-0000-0000-000000000003")
SALARY = uuid.UUID("00000000-0000-0000-0000-000000000004")
TODAY = date(2026, 10, 22)


def _item(day: date, amount: int, category=HOUSING, direction="expense", st="essential", note=None):
    return HistoryItem(
        id=uuid.uuid4(),
        occurred_on=day,
        amount=amount,
        direction=direction,
        category_id=category,
        spending_type=None if direction == "income" else st,
        note=note,
    )


def _detect(items, to_date=TODAY):
    return detect_patterns(items, to_date=to_date, today=TODAY)


def test_case_1_monthly_rent_day_31():
    items = [
        _item(date(2026, 7, 31), 5_000_000, note="Tiền nhà"),
        _item(date(2026, 8, 31), 5_000_000, note="Tiền nhà"),
        _item(date(2026, 9, 30), 5_000_000, note="Tiền nhà"),
    ]
    [pattern] = _detect(items)
    assert pattern.frequency == "monthly"
    assert pattern.amount == 5_000_000
    assert pattern.day_of_month == 31
    assert pattern.day_of_week is None
    assert pattern.confidence >= Fraction(3, 4)
    assert pattern.confidence == 1
    assert pattern.name == "Tiền nhà"
    assert pattern.next_due_on == date(2026, 10, 31)
    assert len(pattern.items) == 3


def test_case_2_amounts_within_10_percent_use_median():
    items = [
        _item(date(2026, 7, 15), 1_000_000, UTILITIES),
        _item(date(2026, 8, 15), 1_080_000, UTILITIES),
        _item(date(2026, 9, 15), 920_000, UTILITIES),
    ]
    [pattern] = _detect(items)
    assert pattern.amount == 1_000_000
    assert pattern.frequency == "monthly"
    assert pattern.day_of_month == 15
    # độ lệch trung bình 53.333 / 1.000.000 = 5,33% → 1 − 0,533 = 0,467
    assert pattern.amount_consistency == Fraction(7, 15)
    assert pattern.confidence == Fraction(2, 5) + Fraction(7, 15) * Fraction(3, 10) + Fraction(
        3, 10
    )
    assert pattern.confidence >= Fraction(3, 4)


def test_case_3_amount_outside_10_percent_not_suggested():
    items = [
        _item(date(2026, 7, 15), 1_000_000, UTILITIES),
        _item(date(2026, 8, 15), 1_250_000, UTILITIES),
        _item(date(2026, 9, 15), 900_000, UTILITIES),
    ]
    assert _detect(items) == []


def test_within_tolerance_is_inclusive_integer_math():
    assert within_tolerance(1_100_000, 1_000_000)
    assert within_tolerance(900_000, 1_000_000)
    assert not within_tolerance(1_100_001, 1_000_000)
    assert not within_tolerance(1_250_000, 1_000_000)


def test_median_amount():
    assert median_amount([1_080_000, 1_000_000, 920_000]) == 1_000_000
    assert median_amount([100, 300]) == 200
    assert median_amount([100, 101]) == 101  # 100,5 làm tròn nửa ra xa 0


def test_amount_consistency_bounds():
    assert amount_consistency([500, 500, 500], 500) == 1
    assert amount_consistency([900, 1100], 1000) == 0
    assert amount_consistency([1000], 0) == 0


def test_weekly_pattern():
    start = date(2026, 8, 3)  # Thứ Hai
    items = [_item(start + timedelta(weeks=i), 150_000, FOOD, note="Đi chợ") for i in range(8)]
    [pattern] = _detect(items, to_date=date(2026, 10, 1))
    assert pattern.frequency == "weekly"
    assert pattern.day_of_week == 1
    assert pattern.day_of_month is None
    assert pattern.next_due_on == date(2026, 10, 26)


def test_monthly_income_salary():
    items = [
        _item(date(2026, m, 5), 25_000_000, SALARY, direction="income", note="Lương")
        for m in (6, 7, 8, 9, 10)
    ]
    [pattern] = _detect(items)
    assert (pattern.direction, pattern.frequency, pattern.day_of_month) == ("income", "monthly", 5)
    assert pattern.spending_type is None
    assert pattern.next_due_on == date(2026, 11, 5)


def test_two_patterns_in_same_group_and_noise_ignored():
    items = []
    for m in (7, 8, 9):
        items.append(_item(date(2026, m, 5), 300_000, UTILITIES, note="Internet"))
        items.append(_item(date(2026, m, 20), 800_000, UTILITIES, note="Tiền điện"))
    items.append(_item(date(2026, 8, 11), 45_000, UTILITIES))
    patterns = _detect(items)
    assert sorted((p.amount, p.day_of_month) for p in patterns) == [(300_000, 5), (800_000, 20)]
    assert {p.name for p in patterns} == {"Internet", "Tiền điện"}


def test_irregular_intervals_not_suggested():
    items = [
        _item(date(2026, 7, 1), 200_000, FOOD),
        _item(date(2026, 7, 3), 200_000, FOOD),
        _item(date(2026, 8, 20), 200_000, FOOD),
        _item(date(2026, 9, 2), 200_000, FOOD),
    ]
    assert _detect(items) == []


def test_only_two_occurrences_not_suggested():
    items = [_item(date(2026, 8, 31), 5_000_000), _item(date(2026, 9, 30), 5_000_000)]
    assert _detect(items) == []


def test_stale_pattern_not_suggested():
    items = [_item(date(2026, m, 10), 5_000_000) for m in (3, 4, 5)]
    assert _detect(items) == []  # lần cuối 10/05, cách 22/10 hơn 2 kỳ


def test_classify_interval():
    freq, consistency, median = classify_interval(
        [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    )
    assert (freq, consistency, median) == ("monthly", 1, Fraction(59, 2))
    assert classify_interval([date(2026, 1, 1), date(2026, 1, 8)])[0] == "weekly"
    assert classify_interval([date(2026, 1, 1), date(2026, 1, 15)])[0] is None


def test_infer_day_of_month():
    assert infer_day_of_month([date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]) == 31
    assert infer_day_of_month([date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]) == 31
    assert infer_day_of_month([date(2026, 7, 5), date(2026, 8, 6), date(2026, 9, 4)]) == 5


def test_amount_clusters_largest_first():
    items = [_item(date(2026, 7, d), 100_000) for d in (1, 2, 3, 4)] + [
        _item(date(2026, 7, d), 500_000) for d in (5, 6, 7)
    ]
    clusters = amount_clusters(items)
    assert [len(c) for c in clusters] == [4, 3]
