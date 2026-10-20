"""API Budget vs Actual (Phase 5) — test case mục 6 của phase-05 + seed scenario."""

from datetime import date

import pytest

from app.scripts import seed_scenario

BUDGETS = "/api/v1/budgets"
TRANSACTIONS = "/api/v1/transactions"
SUMMARY = "/api/v1/dashboard/month-summary"
MONTH_END = "2026-10-31"


@pytest.fixture
def make_budget(client, categories):
    def _make(
        rows: list[tuple[str, str, int]],
        *,
        strategy: str = "fifty_thirty_twenty",
        status: str = "active",
        income: int = 25_000_000,
        month: str = "2026-10-01",
    ) -> dict:
        """`rows`: (slug danh mục, nhóm, planned)."""
        resp = client.post(
            BUDGETS,
            json={
                "period_month": month,
                "strategy": strategy,
                "expected_income": income,
                "status": status,
                "confirm_over_income": True,
                "allocations": [
                    {
                        "group": group,
                        "category_id": categories[slug]["id"],
                        "planned_amount": planned,
                    }
                    for slug, group, planned in rows
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest.fixture
def make_budget_from_strategy(client):
    def _make(strategy: str, *, savings_target: int | None = None, status: str = "active"):
        body = {
            "period_month": "2026-10-01",
            "strategy": strategy,
            "expected_income": 25_000_000,
            "savings_target": savings_target,
        }
        preview = client.post(f"{BUDGETS}/preview", json=body)
        assert preview.status_code == 200, preview.text
        allocations = [
            {k: a[k] for k in ("group", "category_id", "jar_name", "planned_amount")}
            for a in preview.json()["budget"]["allocations"]
        ]
        body.pop("savings_target")
        resp = client.post(BUDGETS, json={**body, "status": status, "allocations": allocations})
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest.fixture
def add_tx(client, categories):
    def _add(
        slug: str,
        amount: int,
        occurred_on: str = "2026-10-10",
        note: str | None = None,
        spending_type: str | None = None,
    ) -> dict:
        category = categories[slug]
        resp = client.post(
            TRANSACTIONS,
            json={
                "direction": category["kind"],
                "amount": amount,
                "occurred_on": occurred_on,
                "category_id": category["id"],
                "spending_type": spending_type,
                "note": note,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _add


def _status(client, budget_id: str, today: str = MONTH_END) -> dict:
    resp = client.get(f"{BUDGETS}/{budget_id}/status", params={"today": today})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _row(status: dict, label: str) -> dict:
    for a in status["allocations"]:
        name = a["category"]["slug"] if a["category"] else a["jar_name"]
        if name == label:
            return a
    raise AssertionError(f"Không có dòng {label}")


# ---------- test case mục 6 ----------


def test_case1_food_over_budget(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000)])
    for amount, day in ((55_000, 3), (60_000, 4), (4_385_000, 5)):
        add_tx("food", amount, f"2026-10-0{day}")

    food = _row(_status(client, budget["id"]), "food")
    assert food["planned"] == 4_000_000
    assert food["actual"] == 4_500_000
    assert food["variance"] == 500_000
    assert food["remaining"] == -500_000
    assert food["used_percent"] == 112.5
    assert food["transaction_count"] == 3
    assert food["status"] == "over_budget"
    # 4.385.000 lớn hơn cả phần vượt → chiếm toàn bộ (share tối đa 1).
    assert food["top_contributor"]["amount"] == 4_385_000
    assert food["top_contributor"]["share"] == 1.0


def test_case2_shopping_top_contributor(client, make_budget, add_tx):
    budget = make_budget([("shopping", "wants", 2_000_000)])
    headphones = add_tx("shopping", 900_000, "2026-10-12", "Tai nghe")
    for amount in (800_000, 650_000, 450_000, 400_000):
        add_tx("shopping", amount)

    shopping = _row(_status(client, budget["id"]), "shopping")
    assert shopping["actual"] == 3_200_000
    assert shopping["variance"] == 1_200_000
    top = shopping["top_contributor"]
    assert top["transaction_id"] == headphones["id"]
    assert top["amount"] == 900_000
    assert top["overspend"] == 1_200_000
    assert top["share"] == 0.75
    assert top["note"] == "Tai nghe"
    assert top["occurred_on"] == "2026-10-12"


def test_no_top_contributor_below_sixty_percent(client, make_budget, add_tx):
    budget = make_budget([("shopping", "wants", 2_000_000)])
    for amount in (700_000, 700_000, 700_000, 700_000):  # vượt 800.000, lớn nhất 87,5%
        add_tx("shopping", amount)
    assert _row(_status(client, budget["id"]), "shopping")["top_contributor"]["share"] == 0.875

    add_tx("shopping", 500_000)  # vượt 1.300.000, lớn nhất 700.000 = 53,8%
    shopping = _row(_status(client, budget["id"]), "shopping")
    assert shopping["status"] == "over_budget"
    assert shopping["top_contributor"] is None


def test_case3_transport_under_budget(client, make_budget, add_tx):
    budget = make_budget([("transport", "essential", 1_000_000)])
    add_tx("transport", 400_000)
    add_tx("transport", 300_000)

    transport = _row(_status(client, budget["id"]), "transport")
    assert transport["actual"] == 700_000
    assert transport["variance"] == -300_000
    assert transport["remaining"] == 300_000
    assert transport["status"] == "on_track"
    assert transport["top_contributor"] is None


def test_case4_income_vs_expected(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000)])
    add_tx("salary", 25_000_000, "2026-10-05")
    add_tx("freelance", 4_000_000, "2026-10-20")
    add_tx("food", 1_000_000)

    totals = _status(client, budget["id"])["totals"]
    assert totals["income_expected"] == 25_000_000
    assert totals["income_actual"] == 29_000_000
    assert totals["income_variance"] == 4_000_000
    assert totals["expense_actual"] == 1_000_000
    assert totals["net_actual"] == 28_000_000


def test_case5_pro_rata_pace(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000)])
    add_tx("food", 3_000_000, "2026-10-14")

    status = _status(client, budget["id"], today="2026-10-15")
    assert status["progress"]["elapsed_days"] == 15
    assert status["progress"]["days_in_month"] == 31
    assert status["progress"]["month_progress"] == pytest.approx(0.48, abs=0.005)
    food = _row(status, "food")
    assert food["expected_to_date"] == 1_935_484
    assert food["used_percent"] == 75.0
    assert food["pace_status"] == "ahead"
    assert food["status"] == "ahead_of_pace"

    food = _row(_status(client, budget["id"], today="2026-10-25"), "food")
    assert food["pace_status"] == "on_track"
    assert food["status"] == "on_track"


def test_case6_envelope_jar_actual(client, make_budget_from_strategy, add_tx):
    budget = make_budget_from_strategy("envelope")
    add_tx("housing", 5_000_000)
    add_tx("food", 4_500_000)
    add_tx("transport", 700_000)
    add_tx("shopping", 1_000_000)

    status = _status(client, budget["id"])
    essential = _row(status, "Essential")
    assert essential["actual"] == 10_200_000
    assert essential["transaction_count"] == 3
    assert essential["scope"]["kind"] == "jar"
    assert {c["slug"] for c in essential["scope"]["categories"]} >= {
        "housing",
        "food",
        "transport",
    }
    assert _row(status, "Shopping")["actual"] == 1_000_000
    assert _row(status, "Fun")["actual"] == 0


def test_case7_savings_not_counted(client, make_budget_from_strategy, add_tx):
    budget = make_budget_from_strategy("envelope")
    add_tx("other", 3_000_000)  # hũ Unexpected 2.000.000 → vượt

    status = _status(client, budget["id"])
    saving = _row(status, "Saving")
    assert saving["planned"] == 5_000_000
    assert saving["actual"] == 0
    assert saving["status"] == "not_tracked"
    assert saving["pace_status"] is None
    assert saving["top_contributor"] is None
    totals = status["totals"]
    assert totals["over_budget_count"] == 1
    assert totals["savings_planned"] == 5_000_000
    assert totals["expense_planned"] == 20_000_000


def test_pyf_group_rows_match_spending_type(client, make_budget_from_strategy, add_tx):
    budget = make_budget_from_strategy("pyf", savings_target=5_000_000)
    add_tx("food", 300_000)  # essential
    add_tx("food", 200_000, spending_type="non_essential")
    add_tx("electronics", 2_500_000, spending_type="irregular")

    status = _status(client, budget["id"])
    assert _row(status, "essential")["actual"] == 300_000
    assert _row(status, "wants")["actual"] == 200_000
    assert _row(status, "irregular")["actual"] == 2_500_000
    assert _row(status, "irregular")["scope"]["spending_types"] == ["irregular"]
    savings = _row(status, "savings")
    assert savings["actual"] == 0
    assert savings["status"] == "not_tracked"
    assert status["totals"]["unbudgeted_actual"] == 0


def test_unbudgeted_expense(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000)])
    add_tx("food", 1_000_000)
    add_tx("gifts", 500_000)

    totals = _status(client, budget["id"])["totals"]
    assert totals["expense_actual"] == 1_500_000
    assert totals["allocated_actual"] == 1_000_000
    assert totals["unbudgeted_actual"] == 500_000
    assert totals["expense_variance"] == 1_500_000 - 4_000_000


def test_transactions_outside_month_ignored(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000)])
    add_tx("food", 1_000_000, "2026-09-30")
    add_tx("food", 2_000_000, "2026-11-01")
    add_tx("food", 100_000, "2026-10-31")
    assert _row(_status(client, budget["id"]), "food")["actual"] == 100_000


def test_case8_no_active_budget(client, make_budget, add_tx):
    add_tx("salary", 25_000_000, "2026-10-05")
    add_tx("food", 1_200_000)

    resp = client.get(f"{BUDGETS}/current/status", params={"today": "2026-10-20"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "budget_not_found"

    summary = client.get(SUMMARY, params={"today": "2026-10-20"}).json()
    assert summary["month"] == "2026-10-01"
    assert summary["income_actual"] == 25_000_000
    assert summary["expense_actual"] == 1_200_000
    assert summary["net_actual"] == 23_800_000
    assert summary["budget_status"] is None
    assert summary["budget"] is None
    assert summary["top_over"] is None

    make_budget([("food", "essential", 4_000_000)], status="draft")
    resp = client.get(f"{BUDGETS}/current/status", params={"today": "2026-10-20"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "budget_not_active"
    summary = client.get(SUMMARY, params={"today": "2026-10-20"}).json()
    assert summary["budget_status"] == "draft"
    assert summary["budget"] is None


def test_current_status_month_param_and_closed(client, make_budget):
    budget = make_budget([("food", "essential", 4_000_000)], month="2026-09-01")
    resp = client.get(
        f"{BUDGETS}/current/status", params={"month": "2026-09-15", "today": "2026-10-20"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["budget_id"] == budget["id"]
    assert data["progress"]["elapsed_days"] == 30  # tháng 9 đã qua

    client.patch(f"{BUDGETS}/{budget['id']}", json={"status": "closed"})
    resp = client.get(
        f"{BUDGETS}/current/status", params={"month": "2026-09-01", "today": "2026-10-20"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


def test_status_unknown_budget(client):
    resp = client.get(f"{BUDGETS}/00000000-0000-0000-0000-000000000000/status")
    assert resp.status_code == 404
    assert resp.json()["code"] == "budget_not_found"


def test_case9_drill_down(client, make_budget, add_tx):
    budget = make_budget([("food", "essential", 4_000_000), ("shopping", "wants", 2_000_000)])
    add_tx("food", 50_000, "2026-10-03", "Phở")
    add_tx("food", 60_000, "2026-10-20", "Bún")
    add_tx("food", 70_000, "2026-10-11", "Cơm")
    add_tx("food", 80_000, "2026-09-28", "Tháng trước")
    add_tx("shopping", 900_000, "2026-10-12")
    food_id = _row(budget_status := _status(client, budget["id"]), "food")["id"]
    assert budget_status["allocations"][0]["id"] == food_id

    resp = client.get(f"/api/v1/budget-allocations/{food_id}/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert [t["occurred_on"] for t in data["items"]] == ["2026-10-20", "2026-10-11", "2026-10-03"]
    assert {t["category"]["slug"] for t in data["items"]} == {"food"}

    page2 = client.get(
        f"/api/v1/budget-allocations/{food_id}/transactions", params={"page": 2, "page_size": 2}
    ).json()
    assert page2["total"] == 3
    assert [t["note"] for t in page2["items"]] == ["Phở"]


def test_drill_down_savings_and_unknown(client, make_budget_from_strategy, add_tx):
    budget = make_budget_from_strategy("pyf", savings_target=5_000_000)
    add_tx("food", 300_000)
    savings = next(a for a in budget["allocations"] if a["group"] == "savings")
    resp = client.get(f"/api/v1/budget-allocations/{savings['id']}/transactions")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = client.get(
        "/api/v1/budget-allocations/00000000-0000-0000-0000-000000000000/transactions"
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "allocation_not_found"


# ---------- seed scenario ----------


@pytest.fixture
def scenario(db) -> str:
    return str(seed_scenario.seed(db, reset=True).id)


def test_seed_scenario_month_end(client, scenario):
    status = _status(client, scenario, today=MONTH_END)
    table = {
        a["category"]["slug"]: (a["planned"], a["actual"], a["variance"], a["status"])
        for a in status["allocations"]
    }
    assert table == {
        "housing": (5_000_000, 5_000_000, 0, "on_track"),
        "food": (4_000_000, 4_500_000, 500_000, "over_budget"),
        "transport": (1_000_000, 700_000, -300_000, "on_track"),
        "shopping": (2_000_000, 3_200_000, 1_200_000, "over_budget"),
        "entertainment": (1_000_000, 600_000, -400_000, "on_track"),
    }
    assert [a["category"]["slug"] for a in status["allocations"]] == [
        "housing",
        "food",
        "transport",
        "shopping",
        "entertainment",
    ]
    assert _row(status, "food")["top_contributor"] is None
    top = _row(status, "shopping")["top_contributor"]
    assert (top["amount"], top["share"], top["note"]) == (900_000, 0.75, "Tai nghe bluetooth")

    totals = status["totals"]
    assert totals["income_expected"] == totals["income_actual"] == 25_000_000
    assert totals["income_variance"] == 0
    assert totals["expense_planned"] == 13_000_000
    assert totals["expense_actual"] == 14_000_000
    assert totals["unbudgeted_actual"] == 0
    assert totals["net_actual"] == 11_000_000
    assert totals["over_budget_count"] == 2


def test_seed_scenario_mid_month_summary(client, scenario):
    params = {"month": "2026-10-01", "today": "2026-10-20"}
    current = client.get(f"{BUDGETS}/current/status", params=params)
    assert current.status_code == 200
    assert current.json()["budget_id"] == scenario

    summary = client.get(SUMMARY, params=params).json()
    assert summary["income_actual"] == 25_000_000
    assert summary["expense_actual"] == 14_000_000
    assert summary["net_actual"] == 11_000_000
    assert summary["budget_status"] == "active"
    assert summary["budget"]["expense_planned"] == 13_000_000
    assert summary["top_over"]["category"]["slug"] == "shopping"
    assert summary["top_over"]["top_contributor"]["amount"] == 900_000
    assert summary["progress"]["elapsed_days"] == 20


def test_seed_scenario_requires_reset_when_month_not_empty(db, scenario):
    with pytest.raises(seed_scenario.ScenarioExistsError):
        seed_scenario.seed(db)
    assert seed_scenario.seed(db, reset=True).period_month == date(2026, 10, 1)
