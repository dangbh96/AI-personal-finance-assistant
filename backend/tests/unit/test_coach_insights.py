"""Hàm thuần của Financial Coach: thống kê trend danh mục, evidence, chi phí token."""

from datetime import date

from app.core.ai_usage import UsageTotals, estimate_cost_vnd
from app.schemas.coach import (
    BudgetLineBrief,
    BudgetStatusOutput,
    CategoryTrendOutput,
    SpendingSummaryItem,
    SpendingSummaryOutput,
)
from app.services import coach_evidence, insight_service
from app.services.insight_service import CategorySeries, build_trend_items

MONTHS = insight_service.trend_months(date(2026, 9, 15), 3)


def _items():
    return build_trend_items(
        MONTHS,
        [
            CategorySeries("food", "Ăn uống", [4_000_000, 4_100_000, 4_200_000]),
            CategorySeries("shopping", "Mua sắm", [1_500_000, 1_000_000, 3_800_000], 2_000_000),
            CategorySeries("entertainment", "Giải trí", [900_000, 1_300_000, 1_100_000]),
        ],
    )


def test_trend_months_and_default_end():
    assert [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)] == MONTHS
    assert insight_service.default_trend_end(date(2026, 1, 20)) == date(2025, 12, 1)
    assert insight_service.trend_months(date(2026, 2, 1), 2) == [date(2026, 1, 1), date(2026, 2, 1)]


def test_trend_statistics_and_volatility_rank():
    items = {i.category_slug: i for i in _items()}
    food, shopping, fun = items["food"], items["shopping"], items["entertainment"]
    assert food.totals_by_month == {
        "2026-07": 4_000_000,
        "2026-08": 4_100_000,
        "2026-09": 4_200_000,
    }
    assert (food.latest_total, food.previous_total, food.delta_vs_previous) == (
        4_200_000,
        4_100_000,
        100_000,
    )
    assert food.delta_vs_previous_pct == 2  # 2,44% → 2
    assert shopping.delta_vs_previous == 2_800_000 and shopping.delta_vs_previous_pct == 280
    assert shopping.average == 2_100_000
    # Population std: Mua sắm ≈ 1.219.289, Giải trí ≈ 163.299, Ăn uống ≈ 81.650.
    assert (shopping.volatility, fun.volatility, food.volatility) == (1_219_289, 163_299, 81_650)
    assert (shopping.volatility_rank, fun.volatility_rank, food.volatility_rank) == (1, 2, 3)
    assert shopping.irregular_total == 2_000_000
    assert [i.category_slug for i in _items()] == ["food", "shopping", "entertainment"]


def test_trend_ties_and_zero_previous():
    items = build_trend_items(
        MONTHS,
        [
            CategorySeries("a", "A", [0, 0, 500_000]),
            CategorySeries("b", "B", [0, 0, 500_000]),
            CategorySeries("c", "C", [100_000, 100_000, 100_000]),
        ],
    )
    by_slug = {i.category_slug: i for i in items}
    assert by_slug["a"].delta_vs_previous_pct is None
    assert (by_slug["a"].volatility_rank, by_slug["b"].volatility_rank) == (1, 2)
    assert by_slug["c"].volatility == 0 and by_slug["c"].volatility_rank == 3


def test_share_and_change_pct():
    assert insight_service.share_pct(1, 3) == 33.3
    assert insight_service.share_pct(5, 0) is None
    assert insight_service.change_pct(1_180_000, 1_000_000) == 18
    assert insight_service.change_pct(5, 0) is None


def _trend_output() -> CategoryTrendOutput:
    return CategoryTrendOutput(
        months=["2026-07", "2026-08", "2026-09"],
        from_date=MONTHS[0],
        to_date=date(2026, 9, 30),
        items=_items(),
        most_volatile="Mua sắm",
    )


def test_select_evidence_keeps_cited_rows_only():
    budget = BudgetStatusOutput(
        available=True,
        month=date(2026, 9, 1),
        reason=None,
        budget_status="active",
        elapsed_days=30,
        days_in_month=30,
        month_progress_pct=100.0,
        income_actual=25_000_000,
        expense_planned=7_000_000,
        expense_actual=9_100_000,
        expense_variance=2_100_000,
        unbudgeted_actual=0,
        over_budget_count=1,
        lines=[
            BudgetLineBrief(
                label="Mua sắm",
                group="wants",
                category_slug="shopping",
                planned=2_000_000,
                actual=3_800_000,
                variance=1_800_000,
                used_percent=190.0,
                status="over_budget",
                pace_status="ahead",
                zone=None,
                comfort_high=None,
                warning_threshold=None,
                top_contributor_note="Nồi chiên",
                top_contributor_amount=2_000_000,
                top_contributor_share_pct=100.0,
            )
        ],
    )
    answer = "Ăn uống 4.200.000 ₫; Mua sắm 3.800.000 ₫, vượt 1,8 triệu; 41,8%."
    evidence, refs = coach_evidence.select_evidence(
        [("get_category_trend", _trend_output()), ("get_budget_status", budget)], answer
    )
    rows = [(e.ref, e.label, e.period, e.metric, e.amount) for e in evidence]
    assert rows == [
        ("E1", "Ăn uống", "09/2026", "Chi tiêu", 4_200_000),
        ("E2", "Mua sắm", "09/2026", "Chi tiêu", 3_800_000),
        ("E3", "Mua sắm", "09/2026", "Thực chi", 3_800_000),
        ("E4", "Mua sắm", "09/2026", "Chênh lệch", 1_800_000),
    ]
    assert refs == [["E1", "E2"], ["E3", "E4"]]
    assert coach_evidence.select_evidence([("x", None)], answer) == ([], [[]])


def test_summaries():
    assert coach_evidence.summarize_result(_trend_output()) == (
        "3 danh mục · 3 tháng (07/2026–09/2026)",
        3,
    )
    summary = SpendingSummaryOutput(
        from_date=date(2026, 9, 1),
        to_date=date(2026, 9, 30),
        group_by="spending_type",
        income_total=0,
        expense_total=100,
        net=-100,
        items=[
            SpendingSummaryItem(
                category_slug=None,
                category_name=None,
                spending_type="irregular",
                total=100,
                transaction_count=1,
                share_pct=100.0,
            )
        ],
    )
    assert coach_evidence.summarize_result(summary) == ("1 loại chi tiêu · 01/09–30/09/2026", 1)
    labels = {r.label for r in coach_evidence.evidence_rows("s", summary)}
    assert labels == {"Tất cả", "Bất thường"}


def test_estimated_cost():
    assert estimate_cost_vnd("gpt-4o", 1_000_000, 0) == 65_000
    assert estimate_cost_vnd("gpt-4o-mini-2024-07-18", 1_000_000, 1_000_000) == 19_500
    assert estimate_cost_vnd("gpt-4o-2024-08-06", 2000, 400) == 234
    assert estimate_cost_vnd("llama3", 10, 10) is None
    assert estimate_cost_vnd(None, 10, 10) is None
    usage = UsageTotals()
    usage.add("gpt-4o-mini", 100, None, 12)
    usage.add("gpt-4o-mini", 50, 20, 8)
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.calls) == (
        150,
        20,
        170,
        2,
    )
    assert usage.llm_latency_ms == 20
