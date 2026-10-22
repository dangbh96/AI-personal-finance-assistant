"""Phase 17: hàm thuần của What-if simulator — số VND chính xác (phase-17 § 6), không DB / AI."""

import uuid
from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.simulator import (
    AddRecurringExpenseParam,
    ChangeGoalDeadlineParam,
    ChangeIncomeParam,
    ReduceCategoryParam,
    ScenarioParam,
    SimulationResult,
)
from app.services import simulator_narrative, simulator_service
from app.services.simulator_service import (
    BaselineSnapshot,
    BudgetLine,
    CategoryInfo,
    ExpenseRow,
    GoalState,
    apply_params,
    compute_goal_completion,
    simulate,
)

FOOD = uuid.uuid4()
HOUSING = uuid.uuid4()
ENTERTAINMENT = uuid.uuid4()
LAPTOP = uuid.uuid4()
TRIP = uuid.uuid4()
START = date(2026, 10, 7)


def _snapshot(goals=None, lines=()) -> BaselineSnapshot:
    """Thu 25.000.000, chi 20.600.000 (Ăn uống 1.500.000) → để dành 4.400.000 / tháng."""
    return BaselineSnapshot(
        start_date=START,
        baseline_from=date(2026, 7, 1),
        baseline_to=date(2026, 9, 30),
        months=3,
        include_irregular=False,
        income=25_000_000,
        rows=(
            ExpenseRow(HOUSING, "Nhà ở", "essential", 19_100_000),
            ExpenseRow(FOOD, "Ăn uống", "non_essential", 1_500_000),
        ),
        goals=tuple(
            goals
            if goals is not None
            else [GoalState(LAPTOP, "Laptop", 1, 22_000_000, date(2027, 3, 31))]
        ),
        budget_month=date(2026, 10, 1) if lines else None,
        budget_lines=tuple(lines),
        categories={
            FOOD: CategoryInfo("Ăn uống", "expense", "essential"),
            HOUSING: CategoryInfo("Nhà ở", "expense", "essential"),
            ENTERTAINMENT: CategoryInfo("Giải trí", "expense", "non_essential"),
        },
    )


def reduce_food(percent=20):
    return ReduceCategoryParam(type="reduce_category", category_id=FOOD, percent=percent)


def test_case_1_reduce_eating_out_20_percent():
    result = simulate(_snapshot(), [reduce_food()])
    assert result.baseline_monthly_savings == 4_400_000
    assert result.delta_monthly_savings == 300_000
    assert result.projected_monthly_savings == 4_700_000
    assert result.applied[0].label == "Giảm Ăn uống 20%"
    assert result.applied[0].delta_monthly_savings == 300_000
    change = result.category_changes[0]
    assert (change.name, change.baseline, change.projected, change.delta) == (
        "Ăn uống",
        1_500_000,
        1_200_000,
        -300_000,
    )


def test_case_2_3_4_goal_completion_days_and_dates():
    before = compute_goal_completion(22_000_000, 4_400_000)
    assert (before.months, before.days) == (5.0, 150)
    after = compute_goal_completion(22_000_000, 4_700_000)
    assert (after.months, after.days) == (4.68, 141)  # 140,43 ngày → làm tròn lên

    impact = simulate(_snapshot(), [reduce_food()]).goal_impacts[0]
    assert (impact.days_before, impact.days_after, impact.days_earlier) == (150, 141, 9)
    assert impact.completion_date_before == date(2027, 3, 6)
    assert impact.completion_date_after == date(2027, 2, 25)
    assert (impact.months_before, impact.months_after) == (5.0, 4.68)
    assert impact.on_track_before and impact.on_track_after  # hạn 31/03/2027


def test_case_5_add_recurring_expense():
    param = AddRecurringExpenseParam(
        type="add_recurring_expense", name="Netflix", amount=199_000, category_id=ENTERTAINMENT
    )
    result = simulate(_snapshot(), [param])
    assert result.projected_monthly_savings == 4_400_000 - 199_000
    assert result.delta_monthly_savings == -199_000
    assert result.projected_monthly_expense == 20_600_000 + 199_000
    assert result.applied[0].label == "Thêm khoản định kỳ “Netflix” 199.000 ₫/tháng"
    assert any(c.name == "Giải trí" and c.delta == 199_000 for c in result.category_changes)
    impact = result.goal_impacts[0]
    assert impact.days_after > impact.days_before and impact.days_earlier < 0


def test_case_6_change_income():
    result = simulate(
        _snapshot(), [ChangeIncomeParam(type="change_income", delta_amount=2_000_000)]
    )
    assert result.projected_monthly_savings == 6_400_000
    assert result.projected_monthly_expense == result.baseline_monthly_expense
    assert result.applied[0].label == "Thu nhập tăng 2.000.000 ₫/tháng"


@pytest.mark.parametrize("percent", [0, 150, -5])
def test_case_7_percent_validation(percent):
    with pytest.raises(ValidationError):
        ReduceCategoryParam(type="reduce_category", category_id=FOOD, percent=percent)


def test_params_apply_in_order_and_combine():
    result = simulate(
        _snapshot(),
        [
            reduce_food(20),
            reduce_food(50),  # 50% của 1.200.000 còn lại
            ChangeIncomeParam(type="change_income", delta_amount=-1_000_000),
        ],
    )
    assert [a.delta_monthly_savings for a in result.applied] == [300_000, 600_000, -1_000_000]
    assert result.delta_monthly_savings == -100_000


def test_income_cannot_go_negative_and_negative_savings_warn():
    projected = apply_params(
        _snapshot(), [ChangeIncomeParam(type="change_income", delta_amount=-30_000_000)]
    )
    assert projected.income == 0
    assert any("không thể âm" in w for w in projected.warnings)
    assert any("cao hơn thu nhập" in w for w in projected.warnings)
    result = simulate(
        _snapshot(), [ChangeIncomeParam(type="change_income", delta_amount=-30_000_000)]
    )
    impact = result.goal_impacts[0]
    assert impact.days_after is None and impact.completion_date_after is None
    assert impact.on_track_after is False and impact.days_earlier is None


def test_reduce_category_without_spending_warns():
    param = ReduceCategoryParam(type="reduce_category", category_id=ENTERTAINMENT, percent=10)
    result = simulate(_snapshot(), [param])
    assert result.delta_monthly_savings == 0
    assert any("không có chi tiêu" in w for w in result.warnings)


def test_goals_waterfall_by_priority():
    goals = [
        GoalState(TRIP, "Du lịch", 2, 8_800_000, date(2027, 6, 30)),
        GoalState(LAPTOP, "Laptop", 1, 22_000_000, date(2027, 3, 31)),
    ]
    impacts = simulate(_snapshot(goals), [reduce_food()]).goal_impacts
    assert [g.name for g in impacts] == ["Laptop", "Du lịch"]
    trip = impacts[1]
    # Du lịch đạt khi đủ 22.000.000 + 8.800.000 = 30.800.000.
    assert (trip.days_before, trip.days_after) == (210, 197)
    assert trip.required_monthly_before == 1_100_000  # 8.800.000 / 8 tháng (10/2026 → 06/2027)


def test_change_goal_deadline_changes_required_and_on_track():
    param = ChangeGoalDeadlineParam(
        type="change_goal_deadline", goal_id=LAPTOP, new_deadline=date(2027, 1, 31)
    )
    result = simulate(_snapshot(), [param])
    impact = result.goal_impacts[0]
    assert result.delta_monthly_savings == 0
    assert impact.deadline_after == date(2027, 1, 31)
    assert impact.required_monthly_before == 4_400_000  # 22.000.000 / 5 tháng
    assert impact.required_monthly_after == 7_400_000  # / 3 tháng → làm tròn 100.000
    assert impact.on_track_before is True and impact.on_track_after is False
    assert result.applied[0].label == "Đổi hạn “Laptop” sang 31/01/2027"


def test_budget_variance_by_category_and_group():
    lines = [
        BudgetLine("Ăn uống", 1_400_000, category_ids=frozenset({FOOD})),
        BudgetLine("Thiết yếu", 19_000_000, spending_types=frozenset({"essential"})),
    ]
    result = simulate(_snapshot(lines=lines), [reduce_food()])
    food, essential = result.budget_variance_after
    assert (food.baseline_actual, food.projected_actual) == (1_500_000, 1_200_000)
    assert (food.variance_before, food.variance_after) == (100_000, -200_000)
    assert (essential.baseline_actual, essential.variance_before) == (19_100_000, 100_000)
    assert result.budget_month == date(2026, 10, 1)


def test_no_goals_no_budget_no_income_warnings():
    snap = _snapshot(goals=[])
    snap = BaselineSnapshot(**{**snap.__dict__, "income": 0})
    result = simulate(snap, [reduce_food()])
    assert result.goal_impacts == []
    text = " ".join(result.warnings)
    assert "Chưa có thu nhập" in text and "Chưa có mục tiêu" in text and "chưa có ngân sách" in text


def test_baseline_period():
    assert simulator_service.baseline_period(date(2026, 10, 7), 3) == (
        date(2026, 7, 1),
        date(2026, 9, 30),
    )
    assert simulator_service.baseline_period(date(2026, 1, 15), 1) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_discriminated_union_parsing():
    adapter = TypeAdapter(ScenarioParam)
    parsed = adapter.validate_python({"type": "change_income", "delta_amount": 2_000_000})
    assert isinstance(parsed, ChangeIncomeParam)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "unknown"})


# ---------- diễn giải (deterministic) ----------


def _result() -> SimulationResult:
    return simulate(_snapshot(), [reduce_food()])


def test_template_narrative_mentions_key_numbers_and_passes_validation():
    """Test case 8 (bản mẫu): có 300.000 và 9 ngày, không "bạn phải"."""
    result = _result()
    narrative = simulator_narrative.template_narrative(result)
    text = " ".join([narrative.observation, narrative.explanation, narrative.action or ""])
    assert "300.000" in text and "9 ngày" in text
    assert "bạn phải" not in text.lower()
    assert simulator_narrative.validate(narrative, result) == []


def test_validate_rejects_invented_numbers_tone_and_risky_advice():
    result = _result()
    good = simulator_narrative.template_narrative(result)
    bad = good.model_copy(
        update={
            "observation": "Bạn phải cắt ăn uống, tiết kiệm thêm 350.000 ₫.",
            "action": "Hãy vay thêm để đầu tư.",
        }
    )
    problems = " ".join(simulator_narrative.validate(bad, result))
    assert "350.000" in problems and "bạn phải" in problems
    assert "vay" in problems and "đầu tư" in problems
    assert "có điều kiện" in problems
    # "vậy" không bị nhầm với "vay".
    ok = good.model_copy(update={"explanation": good.explanation + " Như vậy mục tiêu sớm hơn."})
    assert simulator_narrative.validate(ok, result) == []


def test_allowed_numbers_include_dates_and_months():
    allowed = simulator_narrative.allowed_numbers(_result())
    for value in (300_000, 4_700_000, 9, 150, 141, 2027, 25, 30):
        assert value in allowed
    assert any(abs(float(v) - 4.68) < 1e-9 for v in allowed)
