"""Tool read-only của Financial Coach trên DB test (phase-10 § 6 test case 1, 2)."""

from datetime import date

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.agents.tools import finance_tools
from app.agents.tools.registry import COACH_TOOL_NAMES, CoachToolContext, CoachToolRegistry
from app.ai import openai_client
from app.core.errors import DomainError, NotFoundError
from app.schemas.coach import (
    BudgetAdviceInput,
    BudgetStatusInput,
    CategoryTrendInput,
    RecentReviewsInput,
    SpendingSummaryInput,
)
from app.services import insight_service
from tests import coach_dataset
from tests.coach_dataset import AUGUST, OCTOBER, SEPTEMBER, TODAY


@pytest.fixture
def seeded(db):
    return coach_dataset.seed_all(db)


@pytest.fixture
def no_ai(monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)


def test_category_trend_case_1(db, seeded):
    out = insight_service.get_category_trend(db, CategoryTrendInput(months=3), TODAY)
    assert out.months == ["2026-07", "2026-08", "2026-09"]
    assert (out.from_date, out.to_date) == (date(2026, 7, 1), date(2026, 9, 30))
    items = {i.category_slug: i for i in out.items}
    assert set(items) == {"food", "shopping", "entertainment"}
    assert items["food"].latest_total == 4_200_000
    assert items["shopping"].latest_total == 3_800_000
    assert items["entertainment"].latest_total == 1_100_000
    assert [items[s].volatility_rank for s in ("shopping", "entertainment", "food")] == [1, 2, 3]
    assert out.most_volatile == "Mua sắm"
    assert items["shopping"].irregular_total == 2_000_000
    assert items["shopping"].transaction_count == 5
    # Tháng 10 (đang chạy) không nằm trong chuỗi mặc định.
    assert items["food"].totals_by_month["2026-09"] == 4_200_000


def test_category_trend_filters_and_errors(db, seeded):
    out = insight_service.get_category_trend(
        db, CategoryTrendInput(months=2, category_slug="food", end_month=OCTOBER), TODAY
    )
    assert [i.category_slug for i in out.items] == ["food"]
    assert out.items[0].totals_by_month == {"2026-09": 4_200_000, "2026-10": 600_000}
    empty = insight_service.get_category_trend(
        db, CategoryTrendInput(category_slug="health"), TODAY
    )
    assert empty.items[0].latest_total == 0 and empty.items[0].volatility == 0
    with pytest.raises(NotFoundError):
        insight_service.get_category_trend(db, CategoryTrendInput(category_slug="nope"), TODAY)
    with pytest.raises(NotFoundError):
        insight_service.get_category_trend(db, CategoryTrendInput(category_slug="salary"), TODAY)
    with pytest.raises(DomainError):
        insight_service.get_category_trend(
            db, CategoryTrendInput(end_month=date(2026, 11, 1)), TODAY
        )


def test_budget_status_case_2(db, seeded):
    out = insight_service.get_budget_status(db, BudgetStatusInput(month=SEPTEMBER), TODAY)
    assert out.available and out.budget_status == "active"
    lines = {line.category_slug: line for line in out.lines}
    shopping = lines["shopping"]
    assert (shopping.planned, shopping.actual, shopping.variance) == (
        2_000_000,
        3_800_000,
        1_800_000,
    )
    assert shopping.status == "over_budget" and shopping.label == "Mua sắm"
    assert shopping.top_contributor_note == "Nồi chiên"
    assert shopping.top_contributor_amount == 2_000_000
    assert shopping.top_contributor_share_pct == 100.0
    assert shopping.zone is None  # chưa tính vùng
    assert (out.expense_planned, out.expense_actual, out.expense_variance) == (
        7_000_000,
        9_100_000,
        2_100_000,
    )
    assert out.month_progress_pct == 100.0
    # Không tự sửa budget.
    db.expire_all()
    planned = {a.category.slug: a.planned_amount for a in seeded[SEPTEMBER].allocations}
    assert planned == {"food": 4_000_000, "shopping": 2_000_000, "entertainment": 1_000_000}


def test_budget_status_current_month_and_missing(db, seeded):
    current = insight_service.get_budget_status(db, BudgetStatusInput(), TODAY)
    assert current.month == OCTOBER and current.elapsed_days == 5
    assert current.month_progress_pct == 16.1
    missing = insight_service.get_budget_status(db, BudgetStatusInput(month=AUGUST), TODAY)
    assert not missing.available and missing.lines == []
    assert "08/2026" in (missing.reason or "")


def test_spending_summary(db, seeded):
    by_category = insight_service.get_spending_summary(
        db, SpendingSummaryInput(from_date=SEPTEMBER, to_date=date(2026, 9, 30))
    )
    assert (by_category.income_total, by_category.expense_total, by_category.net) == (
        25_000_000,
        9_100_000,
        15_900_000,
    )
    assert [
        (i.category_slug, i.total, i.transaction_count, i.share_pct) for i in by_category.items
    ] == [
        ("food", 4_200_000, 2, 46.2),
        ("shopping", 3_800_000, 3, 41.8),
        ("entertainment", 1_100_000, 1, 12.1),
    ]
    by_type = insight_service.get_spending_summary(
        db,
        SpendingSummaryInput(
            from_date=SEPTEMBER, to_date=date(2026, 9, 30), group_by="spending_type"
        ),
    )
    assert {i.spending_type: i.total for i in by_type.items} == {
        "essential": 4_200_000,
        "irregular": 2_000_000,
        "non_essential": 2_900_000,
    }
    with pytest.raises(DomainError):
        insight_service.get_spending_summary(
            db, SpendingSummaryInput(from_date=OCTOBER, to_date=SEPTEMBER)
        )
    with pytest.raises(DomainError):
        insight_service.get_spending_summary(
            db, SpendingSummaryInput(from_date=date(2025, 1, 1), to_date=OCTOBER)
        )


def test_budget_advice_and_reviews(client, db, seeded, no_ai):
    empty = insight_service.get_budget_advice(db, BudgetAdviceInput())
    assert empty.items == [] and "/budget/advice" in (empty.note or "")
    assert insight_service.get_recent_reviews(db, RecentReviewsInput()).items == []

    resp = client.post(
        "/api/v1/budget/advice/generate",
        json={"month": "2026-09-01", "today": TODAY.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    advice = insight_service.get_budget_advice(db, BudgetAdviceInput())
    assert advice.month == SEPTEMBER and len(advice.items) == 3
    shopping = next(a for a in advice.items if a.label == "Mua sắm")
    assert (shopping.planned_amount, shopping.actual_amount, shopping.variance) == (
        2_000_000,
        3_800_000,
        1_800_000,
    )
    assert shopping.verdict == "one_off" and shopping.verdict_label == "Khoản bất thường một lần"
    assert insight_service.get_budget_advice(db, BudgetAdviceInput(status="accepted")).items == []

    resp = client.post(
        "/api/v1/reviews/monthly", json={"month": "2026-09-01", "today": TODAY.isoformat()}
    )
    assert resp.status_code == 200, resp.text
    reviews = insight_service.get_recent_reviews(db, RecentReviewsInput(kind="monthly"))
    assert len(reviews.items) == 1
    review = reviews.items[0]
    assert (review.kind, review.period_start, review.expense) == ("monthly", SEPTEMBER, 9_100_000)
    assert review.top_categories[0].category_name == "Ăn uống"
    assert review.observation
    assert insight_service.get_recent_reviews(db, RecentReviewsInput(kind="weekly")).items == []


def test_registry_builds_read_only_tools_and_skips_future(db):
    ctx = CoachToolContext(db=db, today=TODAY)
    tools = finance_tools.default_registry().build(ctx)
    names = [t.name for t in tools]
    assert names == [
        "get_spending_summary",
        "get_budget_status",
        "get_category_trend",
        "get_budget_advice",
        "get_recent_reviews",
        "get_goals",
    ]
    assert {"get_goals", "search_transactions", "search_knowledge", "simulate"} <= set(
        COACH_TOOL_NAMES
    )
    schema = convert_to_openai_tool(tools[2])["function"]
    assert schema["name"] == "get_category_trend"
    props = schema["parameters"]["properties"]
    assert set(props) == {"months", "category_slug", "end_month"}
    assert props["months"]["maximum"] == 12

    registry = CoachToolRegistry()
    registry.register("get_goals", finance_tools.budget_status_tool)
    assert [t.name for t in registry.build(ctx, ["get_goals", "simulate"])] == ["get_budget_status"]


def test_tool_invocation_records_output(db, seeded):
    ctx = CoachToolContext(db=db, today=TODAY)
    trend = finance_tools.category_trend_tool(ctx)
    ctx.recorder.begin("c1", "get_category_trend", {"months": 3})
    raw = trend.invoke({"months": 3})
    ctx.recorder.finish("c1", 5, None)
    record = ctx.recorder.ordered()[0]
    assert record.output is not None and record.error is None
    assert '"latest_total":4200000' in raw
