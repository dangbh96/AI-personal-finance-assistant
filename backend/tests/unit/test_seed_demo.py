from collections import Counter
from datetime import date

from app.scripts.seed_demo import INCOME_SLUGS, demo_period, generate


def test_demo_period_covers_full_months_plus_current():
    assert demo_period(date(2026, 10, 8), 3) == (date(2026, 7, 1), date(2026, 10, 8))
    assert demo_period(date(2026, 1, 31), 1) == (date(2025, 12, 1), date(2026, 1, 31))


def test_generate_is_deterministic_and_patterned():
    start, end = date(2026, 7, 1), date(2026, 9, 30)

    demo = generate(start, end, seed=42)

    assert demo == generate(start, end, seed=42)
    assert 120 <= len(demo) <= 200
    assert all(start <= t.occurred_on <= end for t in demo)
    assert all(isinstance(t.amount, int) and t.amount > 0 for t in demo)
    assert all(t.amount % 1000 == 0 for t in demo)

    salaries = [t.occurred_on for t in demo if t.category_slug == "salary"]
    rents = [t.occurred_on for t in demo if t.category_slug == "housing"]
    assert salaries == [date(2026, m, 5) for m in (7, 8, 9)]
    assert rents == [date(2026, m, 1) for m in (7, 8, 9)]

    assert all(t.spending_type is None for t in demo if t.category_slug in INCOME_SLUGS)
    counts = Counter(t.category_slug for t in demo)
    assert counts["food"] > 60
    assert any(t.spending_type == "irregular" for t in demo)
