"""Budget engine — phép tính thuần (không DB, không AI)."""

import uuid

import pytest

from app.core.errors import DomainError
from app.schemas.budget import BudgetAllocationInput
from app.services import budget_service as bs
from app.services.money import allocate_by_weights, format_vnd

INCOME = 25_000_000


def _amounts(rows: list[BudgetAllocationInput]) -> dict[str, int]:
    return {row.jar_name or str(row.category_id): row.planned_amount for row in rows}


# ---------- allocate_by_weights ----------


@pytest.mark.parametrize(
    ("total", "weights", "step", "expected"),
    [
        (25_000_000, [50, 30, 20], 1000, [12_500_000, 7_500_000, 5_000_000]),
        (10_000, [1, 1, 1], 1000, [4000, 3000, 3000]),
        (10_500, [1, 1], 1000, [5500, 5000]),  # phần lẻ < step vào phần trọng số lớn nhất
        (0, [50, 30, 20], 1000, [0, 0, 0]),
        (7, [1, 2], 1, [2, 5]),
    ],
)
def test_allocate_by_weights(total, weights, step, expected):
    assert allocate_by_weights(total, weights, step) == expected


@pytest.mark.parametrize("total", [1, 999, 1_001, 12_345_678, 33_333_333, 10**12 + 7])
def test_allocate_by_weights_sums_exactly(total):
    amounts = allocate_by_weights(total, [52, 12, 8, 20, 8], 1000)
    assert sum(amounts) == total
    assert all(a >= 0 for a in amounts)
    assert all(isinstance(a, int) for a in amounts)


@pytest.mark.parametrize(("weights", "step"), [([], 1), ([0, 0], 1), ([-1, 2], 1), ([1], 0)])
def test_allocate_by_weights_rejects_invalid(weights, step):
    with pytest.raises(ValueError):
        allocate_by_weights(100, weights, step)


def test_format_vnd():
    assert format_vnd(2_000_000) == "2.000.000 ₫"
    assert format_vnd(-500) == "-500 ₫"


# ---------- chiến lược với thu nhập 25.000.000 ----------


def test_envelope_preset_25m():
    rows = bs.create_envelope_budget(INCOME)
    assert _amounts(rows) == {
        "Essential": 13_000_000,
        "Fun": 3_000_000,
        "Shopping": 2_000_000,
        "Saving": 5_000_000,
        "Unexpected": 2_000_000,
    }
    assert [row.group for row in rows] == ["essential", "wants", "wants", "savings", "irregular"]
    assert all(row.category_id is None for row in rows)


def test_fifty_thirty_twenty_25m():
    rows = bs.create_fifty_thirty_twenty_reference(INCOME)
    assert _amounts(rows) == {
        "essential": 12_500_000,
        "wants": 7_500_000,
        "savings": 5_000_000,
    }
    assert all(row.jar_name == row.group for row in rows)


def test_pyf_25m_savings_first():
    rows = bs.create_pyf_budget(INCOME, 5_000_000)
    assert rows[0].group == "savings"
    assert _amounts(rows) == {
        "savings": 5_000_000,
        "essential": 12_000_000,
        "wants": 6_000_000,
        "irregular": 2_000_000,
    }
    totals = bs.compute_totals(INCOME, rows)
    assert totals.planned_total == INCOME
    assert totals.planned_total - totals.by_group.savings == 20_000_000


def test_pyf_savings_target_exceeds_income():
    with pytest.raises(DomainError) as exc:
        bs.create_pyf_budget(INCOME, 30_000_000)
    assert exc.value.code == "savings_target_exceeds_income"


def test_pyf_savings_target_equal_income():
    rows = bs.create_pyf_budget(INCOME, INCOME)
    assert _amounts(rows) == {"savings": INCOME, "essential": 0, "wants": 0, "irregular": 0}


def test_generate_pyf_requires_savings_target():
    with pytest.raises(DomainError) as exc:
        bs.generate_allocations("pyf", INCOME, None)
    assert exc.value.code == "savings_target_required"


@pytest.mark.parametrize("strategy", ["envelope", "fifty_thirty_twenty", "pyf"])
@pytest.mark.parametrize("income", [0, 1_234_567, 17_500_000, 99_999_999])
def test_strategies_never_exceed_income(strategy, income):
    rows = bs.generate_allocations(strategy, income, income // 5)
    assert sum(row.planned_amount for row in rows) == income


# ---------- tổng, tham khảo 50/30/20, vượt thu nhập ----------


def test_compute_totals_and_unallocated():
    rows = [
        BudgetAllocationInput(group="essential", jar_name="essential", planned_amount=10_000_000),
        BudgetAllocationInput(group="savings", jar_name="savings", planned_amount=3_000_000),
    ]
    totals = bs.compute_totals(INCOME, rows)
    assert totals.planned_total == 13_000_000
    assert totals.unallocated == 12_000_000
    assert totals.by_group.essential == 10_000_000
    assert totals.by_group.wants == 0
    assert bs.savings_total(rows) == 3_000_000


def test_reference_comparison_counts_irregular_as_wants():
    rows = bs.create_pyf_budget(INCOME, 5_000_000)
    ref = bs.compare_with_reference(INCOME, rows)
    assert (ref.essential, ref.wants, ref.savings) == (12_500_000, 7_500_000, 5_000_000)
    by_group = {c.group: c for c in ref.comparison}
    assert by_group["essential"].planned == 12_000_000
    assert by_group["essential"].difference == -500_000
    assert by_group["wants"].planned == 8_000_000  # 6.000.000 wants + 2.000.000 irregular
    assert by_group["wants"].difference == 500_000
    assert by_group["savings"].difference == 0


def test_over_income_amount_27m():
    rows = bs.create_envelope_budget(INCOME)
    rows[0] = rows[0].model_copy(update={"planned_amount": 15_000_000})
    assert bs.over_income_amount(INCOME, rows) == 2_000_000
    assert bs.over_income_amount(INCOME, bs.create_envelope_budget(INCOME)) == 0


# ---------- phạm vi khớp giao dịch (cho Phase 5) ----------


def test_allocation_scope():
    food, housing = uuid.uuid4(), uuid.uuid4()
    jars = {"Essential": [food, housing], "Saving": []}

    category_row = BudgetAllocationInput(group="essential", category_id=food, planned_amount=1)
    scope = bs.allocation_scope("pyf", category_row, jars)
    assert scope.kind == "category"
    assert scope.category_ids == {food}

    jar_row = BudgetAllocationInput(group="essential", jar_name="Essential", planned_amount=1)
    scope = bs.allocation_scope("envelope", jar_row, jars)
    assert scope.kind == "jar"
    assert scope.category_ids == {food, housing}
    assert not scope.spending_types

    saving_jar = BudgetAllocationInput(group="savings", jar_name="Saving", planned_amount=1)
    assert bs.allocation_scope("envelope", saving_jar, jars).category_ids == frozenset()

    group_row = BudgetAllocationInput(group="wants", jar_name="wants", planned_amount=1)
    scope = bs.allocation_scope("fifty_thirty_twenty", group_row, jars)
    assert scope.kind == "group"
    assert scope.spending_types == {"non_essential"}

    savings_row = BudgetAllocationInput(group="savings", jar_name="savings", planned_amount=1)
    assert bs.allocation_scope("pyf", savings_row, jars).spending_types == frozenset()


# ---------- schema ----------


def test_allocation_requires_exactly_one_of_category_or_jar():
    with pytest.raises(ValueError):
        BudgetAllocationInput(group="essential", planned_amount=1)
    with pytest.raises(ValueError):
        BudgetAllocationInput(
            group="essential", category_id=uuid.uuid4(), jar_name="x", planned_amount=1
        )
