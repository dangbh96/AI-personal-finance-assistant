"""Metrics review tháng (Phase 7) — hàm thuần, không cần DB / OpenAI (phase-07 § 6, test 1–4)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.review import (
    BudgetLineSummary,
    FlaggedTransaction,
    MonthlyBudgetSummary,
    MonthlyReviewMetrics,
    ReviewNarrativeOutput,
    WeeklyReflectionDigest,
)
from app.services import review_metrics, review_narrative
from app.services.review_metrics import increase_driver, share_pct
from tests.monthly_dataset import (
    OCT_ITEMS,
    OCTOBER,
    SEP_ITEMS,
    SEPTEMBER,
    TODAY,
)
from tests.review_dataset import Item, to_rows


def _monthly(
    current_items=OCT_ITEMS,
    previous_items=SEP_ITEMS,
    month=OCTOBER,
    today=TODAY,
    budget=None,
    reflections=(),
) -> MonthlyReviewMetrics:
    current, previous = to_rows(current_items), to_rows(previous_items)
    period = review_metrics.compute_period_metrics("month", month, current, previous, today)
    metrics = review_metrics.build_review_metrics(
        period, current, budget=budget, reflections=reflections
    )
    assert isinstance(metrics, MonthlyReviewMetrics)
    return metrics


def _budget() -> MonthlyBudgetSummary:
    food = BudgetLineSummary(
        allocation_id=uuid.uuid4(),
        label="Ăn uống",
        group="essential",
        planned=4_000_000,
        actual=4_500_000,
        variance=500_000,
        used_percent=112.5,
        status="over_budget",
    )
    return MonthlyBudgetSummary(
        budget_id=uuid.uuid4(),
        status="active",
        strategy="fifty_thirty_twenty",
        expense_planned=6_000_000,
        expense_actual=20_608_000,
        expense_variance=14_608_000,
        unbudgeted_actual=15_000_000,
        over_budget_count=1,
        lines=[food],
        over_lines=[food],
    )


def _flagged(amount: int, note: str = "Ăn tối nhà hàng", tx_id=None) -> FlaggedTransaction:
    return FlaggedTransaction(
        id=tx_id or uuid.uuid4(),
        occurred_on=date(2026, 10, 9),
        note=note,
        amount=amount,
        category_name="Ăn uống",
        spending_type="non_essential",
    )


def _digest(week_start: date, answer: str, flagged=()) -> WeeklyReflectionDigest:
    return WeeklyReflectionDigest(
        reflection_id=uuid.uuid4(),
        weekly_review_id=uuid.uuid4(),
        week_start=week_start,
        question="Có khoản nào trong tuần này bạn thấy không đáng tiền không?",
        answer=answer,
        flagged=list(flagged),
    )


# ---------- test case 1–4 ----------


def test_saved_and_savings_rate():
    m = _monthly(SEP_ITEMS, (), SEPTEMBER)
    assert (m.income, m.expense) == (25_000_000, 18_400_000)
    assert m.saved == 6_600_000
    assert m.savings_rate_pct == 26.4


def test_spending_type_breakdown_percent():
    m = _monthly(SEP_ITEMS, (), SEPTEMBER)
    assert m.by_spending_type.model_dump() == {
        "essential": 9_200_000,
        "non_essential": 6_100_000,
        "irregular": 3_100_000,
    }
    assert m.spending_type_pct.model_dump() == {
        "essential": 50.0,
        "non_essential": 33.2,
        "irregular": 16.8,
    }


def test_vs_previous_month():
    m = _monthly()
    assert (m.expense, m.previous_expense) == (20_608_000, 18_400_000)
    assert m.expense_change_pct == 12
    assert (m.income_change, m.income_change_pct) == (0, 0)
    assert (m.saved, m.previous_saved, m.saved_change) == (4_392_000, 6_600_000, -2_208_000)
    assert (m.savings_rate_pct, m.previous_savings_rate_pct) == (17.6, 26.4)
    assert (m.regular_expense, m.previous_regular_expense) == (5_608_000, 15_300_000)
    assert m.regular_expense_change_pct == -63
    assert m.irregular_change == 11_900_000
    assert m.increase_driver == "irregular"


def test_irregular_items_largest_first():
    m = _monthly()
    top = m.irregular_items[0]
    assert (top.amount, top.category_slug, top.note) == (15_000_000, "electronics", "Laptop")
    assert top.spending_type == "irregular"
    assert len(m.irregular_items) == 1

    sep = _monthly(SEP_ITEMS, (), SEPTEMBER)
    assert [(t.note, t.amount) for t in sep.irregular_items] == [
        ("Khám răng", 2_000_000),
        ("Sửa xe máy", 1_100_000),
    ]


# ---------- quy tắc biên ----------


def test_share_pct_rounding_and_zero():
    assert share_pct(1, 3) == 33.3
    assert share_pct(2, 3) == 66.7
    assert share_pct(1, 0) is None
    assert share_pct(-2_000_000, 10_000_000) == -20.0


def test_no_income_and_overspent_month():
    items = (Item(date(2026, 10, 3), "food", 500_000, "Đi chợ"),)
    m = _monthly(items, (), OCTOBER)
    assert (m.saved, m.savings_rate_pct) == (-500_000, None)
    assert m.expense_change_pct is None
    assert m.increase_driver is None
    assert m.spending_type_pct.essential == 100.0


def test_empty_month_has_null_percents():
    m = _monthly((), (), OCTOBER)
    assert m.spending_type_pct.model_dump() == {
        "essential": None,
        "non_essential": None,
        "irregular": None,
    }
    assert (m.increase_driver, m.irregular_items, m.budget) == (None, [], None)


@pytest.mark.parametrize(
    ("expense_change", "irregular_change", "previous", "expected"),
    [
        (2_208_000, 11_900_000, 18_400_000, "irregular"),
        (1_000_000, 500_000, 5_000_000, "irregular"),
        (1_000_000, 499_999, 5_000_000, "regular"),
        (1_000_000, -200_000, 5_000_000, "regular"),
        (1_000_000, 1_000_000, 0, None),
        (0, 5_000_000, 5_000_000, None),
        (-300_000, 0, 5_000_000, None),
    ],
)
def test_increase_driver(expense_change, irregular_change, previous, expected):
    assert increase_driver(expense_change, irregular_change, previous) == expected


def test_monthly_metrics_reject_week_period():
    current = to_rows(OCT_ITEMS)
    period = review_metrics.compute_period_metrics("week", date(2026, 10, 5), current, [], TODAY)
    review = review_metrics.build_review_metrics(period, current)
    assert not isinstance(review, MonthlyReviewMetrics)
    with pytest.raises(ValueError):
        review_metrics.compute_monthly_metrics(review, current)


def test_budget_and_weekly_reflections_are_carried_with_dedup_totals():
    shared = uuid.uuid4()
    reflections = [
        _digest(date(2026, 10, 5), "Bữa tối hơi đắt", [_flagged(300_000, tx_id=shared)]),
        _digest(date(2026, 10, 12), "Ổn", [_flagged(300_000), _flagged(300_000, tx_id=shared)]),
        _digest(date(2026, 10, 19), "Đặt đồ ăn muộn", [_flagged(300_000)]),
        _digest(date(2026, 10, 26), "Không có gì"),
    ]
    m = _monthly(budget=_budget(), reflections=reflections)
    assert m.budget is not None and m.budget.over_lines[0].variance == 500_000
    assert [r.answer for r in m.weekly_reflections] == [r.answer for r in reflections]
    assert (m.flagged_count, m.flagged_total) == (3, 900_000)


# ---------- số được phép / kiểm tra narrative ----------


def _narrative(**overrides) -> ReviewNarrativeOutput:
    data = {
        "observation": "Tháng 10/2026 bạn thu 25.000.000 ₫, chi 20.608.000 ₫, còn lại "
        "4.392.000 ₫ (tỉ lệ tiết kiệm 17,6%). Chi tiêu cao hơn tháng trước 12%.",
        "explanation": "Phần lớn mức tăng đến từ khoản mua laptop 15.000.000 ₫, một khoản bất "
        "thường. Thiết yếu chiếm 21,6%.",
        "notice": ["Ăn uống vượt ngân sách 500.000 ₫."],
        "action": "Nếu bạn muốn, bạn có thể xem phần tư vấn điều chỉnh ngân sách.",
        "reflection_question": review_narrative.MONTHLY_REFLECTION_QUESTION,
        "tone": "neutral",
    }
    return ReviewNarrativeOutput(**{**data, **overrides})


def test_allowed_numbers_include_monthly_values_but_not_ids():
    budget = _budget()
    m = _monthly(budget=budget, reflections=[_digest(date(2026, 10, 5), "x", [_flagged(1)])])
    allowed = review_narrative.allowed_numbers(m)
    for value in ("17.6", "26.4", "12", "15000000", "500000", "4392000", "21.6"):
        assert Decimal(value) in allowed, value
    assert Decimal(20_000_000) not in allowed
    payload = review_narrative.metrics_payload(m)
    assert "budget_id" not in payload["budget"]
    assert "allocation_id" not in payload["budget"]["lines"][0]
    assert "id" not in payload["irregular_items"][0]
    assert "reflection_id" not in payload["weekly_reflections"][0]


def test_validate_monthly_narrative_ok():
    m = _monthly(budget=_budget())
    assert review_narrative.validate_narrative(_narrative(), m) == []


def test_validate_requires_irregular_driver_when_increase_is_one_off():
    m = _monthly(budget=_budget())
    narrative = _narrative(explanation="Chi tiêu tăng do bạn mua sắm nhiều hơn.")
    problems = review_narrative.validate_narrative(narrative, m)
    assert any("khoản bất thường" in p and "15.000.000" in p for p in problems)

    in_millions = _narrative(explanation="Phần lớn mức tăng đến từ laptop 15 triệu.")
    assert review_narrative.validate_narrative(in_millions, m) == []


@pytest.mark.parametrize(
    "text",
    [
        "Bạn kém kỷ luật với ngân sách ăn uống.",
        "Ngân sách sai ngay từ đầu.",
        "Kết luận: adjust_budget cho Ăn uống.",
    ],
)
def test_validate_rejects_verdict_phrases(text):
    m = _monthly(budget=_budget())
    problems = review_narrative.validate_narrative(_narrative(notice=[text]), m)
    assert any("cụm từ phán xét" in p for p in problems)


def test_validate_rejects_invented_number():
    m = _monthly(budget=_budget())
    problems = review_narrative.validate_narrative(
        _narrative(notice=["Bạn có thể tiết kiệm 20.000.000 ₫."]), m
    )
    assert any("20.000.000" in p for p in problems)


# ---------- bản dự phòng ----------


def test_fallback_month_mentions_laptop_and_passes_validation():
    reflections = [
        _digest(date(2026, 10, 5), "Bữa tối hơi đắt", [_flagged(300_000), _flagged(300_000)])
    ]
    m = _monthly(budget=_budget(), reflections=reflections)
    n = review_narrative.fallback_narrative(m, "AI_NOT_CONFIGURED")
    assert review_narrative.validate_narrative(n, m) == []
    assert n.observation.startswith(
        "Tháng 10/2026 bạn thu 25.000.000 ₫, chi 20.608.000 ₫, còn lại 4.392.000 ₫ "
        "(tỉ lệ tiết kiệm 17,6%)."
    )
    assert "cao hơn tháng trước 12%" in n.observation
    assert "“Laptop” 15.000.000 ₫ (Điện tử, 10/10)" in n.explanation
    assert "chi thường xuyên thấp hơn tháng trước 63%" in n.explanation
    assert "thiết yếu 4.448.000 ₫ (21,6%)" in n.explanation
    assert n.notice[0] == (
        "Ăn uống vượt ngân sách 500.000 ₫ (thực chi 4.500.000 ₫ / kế hoạch 4.000.000 ₫)."
    )
    assert "đánh dấu 2 khoản chưa đáng tiền, tổng 600.000 ₫" in n.notice[1]
    assert n.action is not None and "tư vấn điều chỉnh ngân sách" in n.action
    assert n.reflection_question == review_narrative.MONTHLY_REFLECTION_QUESTION


@pytest.mark.parametrize(
    ("current", "previous", "month", "today"),
    [
        ((), (), OCTOBER, TODAY),
        (SEP_ITEMS, (), SEPTEMBER, TODAY),
        (SEP_ITEMS, OCT_ITEMS, SEPTEMBER, TODAY),
        (OCT_ITEMS, SEP_ITEMS, OCTOBER, date(2026, 10, 20)),
        ((Item(date(2026, 10, 3), "food", 500_000, "Đi chợ"),), (), OCTOBER, TODAY),
    ],
)
def test_fallback_month_always_valid(current, previous, month, today):
    m = _monthly(current, previous, month, today)
    n = review_narrative.fallback_narrative(m, "validation_failed")
    assert review_narrative.validate_narrative(n, m) == []
    assert 1 <= len(n.notice) <= 3
