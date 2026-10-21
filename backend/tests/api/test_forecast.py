"""API lịch dòng tiền + dự báo số dư (phase-12 § 6 test case 6, 7) — DB test thật, không AI."""

import pytest

FC = "/api/v1/forecast"
SETTINGS = "/api/v1/settings/forecast"
REC = "/api/v1/recurring-transactions"
OCT_1 = "2026-10-01"


@pytest.fixture
def cat(categories) -> dict[str, str]:
    return {slug: c["id"] for slug, c in categories.items()}


def _recurring(client, cat, name, amount, slug, day, next_due, direction="expense"):
    resp = client.post(
        f"{REC}?today={OCT_1}",
        json={
            "name": name,
            "direction": direction,
            "amount": amount,
            "category_id": cat[slug],
            "frequency": "monthly",
            "day_of_month": day,
            "next_due_on": next_due,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _tx(client, cat, slug, amount, day, direction="expense", spending_type=None, note=None):
    body = {
        "direction": direction,
        "amount": amount,
        "occurred_on": day,
        "category_id": cat[slug],
        "note": note,
    }
    if spending_type:
        body["spending_type"] = spending_type
    resp = client.post("/api/v1/transactions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _settings(client, today=OCT_1, **body):
    resp = client.patch(f"{SETTINGS}?today={today}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _laptop_goal(client):
    goal = client.post(
        f"/api/v1/goals?today={OCT_1}",
        json={"name": "Laptop", "target_amount": 30_000_000, "deadline": "2027-03-22"},
    )
    assert goal.status_code == 201, goal.text
    resp = client.post(
        f"/api/v1/goals/{goal.json()['id']}/contributions?today={OCT_1}",
        json={"amount": 8_000_000, "contributed_on": "2026-09-15"},
    )
    assert resp.status_code == 201, resp.text
    return goal.json()


@pytest.fixture
def scenario(client, cat):
    """Test case 6: số dư 12tr (01/10), lương 25tr ngày 5, nhà 5tr ngày 1, mục tiêu 4,4tr ngày 10,
    chi biến đổi 6tr / 30 ngày tháng 9 = 200.000 / ngày."""
    _settings(client, starting_balance=12_000_000, low_balance_threshold=1_000_000)
    rent = _recurring(client, cat, "Tiền nhà", 5_000_000, "housing", 1, "2026-10-01")
    salary = _recurring(
        client, cat, "Lương", 25_000_000, "salary", 5, "2026-10-05", direction="income"
    )
    _laptop_goal(client)
    _tx(client, cat, "food", 3_000_000, "2026-09-01", note="Đi chợ")
    _tx(client, cat, "food", 3_000_000, "2026-09-15", note="Đi chợ")
    _tx(client, cat, "electronics", 10_000_000, "2026-09-20", spending_type="irregular")
    _tx(client, cat, "housing", 5_000_000, "2026-09-01", note="Tiền nhà")  # khớp khoản định kỳ
    return {"rent": rent, "salary": salary}


def _points(body):
    return {p["date"]: p for p in body["points"]}


def test_settings_defaults_and_update(client):
    assert client.get(SETTINGS).json() == {
        "starting_balance": None,
        "starting_balance_on": None,
        "low_balance_threshold": 1_000_000,
        "goal_saving_day_of_month": 10,
    }
    updated = _settings(client, today="2026-10-22", starting_balance=12_000_000)
    assert (updated["starting_balance"], updated["starting_balance_on"]) == (
        12_000_000,
        "2026-10-22",
    )
    updated = _settings(
        client,
        starting_balance=-500_000,
        starting_balance_on="2026-10-01",
        low_balance_threshold=2_000_000,
        goal_saving_day_of_month=31,
    )
    assert updated == {
        "starting_balance": -500_000,
        "starting_balance_on": "2026-10-01",
        "low_balance_threshold": 2_000_000,
        "goal_saving_day_of_month": 31,
    }
    cleared = _settings(client, starting_balance=None)
    assert (cleared["starting_balance"], cleared["starting_balance_on"]) == (None, None)


@pytest.mark.parametrize(
    "body",
    [
        {"low_balance_threshold": -1},
        {"goal_saving_day_of_month": 0},
        {"goal_saving_day_of_month": 32},
        {"starting_balance": "12tr"},
        {"starting_balance": 1.5},
        {"currency": "USD"},
    ],
)
def test_settings_validation(client, body):
    resp = client.patch(SETTINGS, json=body)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_case_6_forecast_end_to_end(client, scenario):
    resp = client.get(f"{FC}?days=30&start_date={OCT_1}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["starting_balance_set"] is True
    assert (body["starting_balance"], body["opening_balance"]) == (12_000_000, 12_000_000)
    assert body["average_daily_variable_spending"] == 200_000
    assert (body["variable_history_days"], body["insufficient_history"]) == (30, False)
    assert body["monthly_goal_saving"] == 4_400_000
    points = _points(body)
    assert len(points) == 30
    assert points["2026-10-10"]["projected_balance"] == 25_600_000
    assert points["2026-10-01"]["delta_expense"] == 5_000_000
    assert points["2026-10-05"]["delta_income"] == 25_000_000
    assert points["2026-10-10"]["delta_goal_saving"] == 4_400_000
    assert [e["icon"] for e in points["2026-10-10"]["events"]] == ["🎯"]
    assert points["2026-10-10"]["events"][0]["label"] == "Để dành mục tiêu: Laptop"
    assert body["low_balance_warning_day"] is None
    assert body["end_balance"] == 12_000_000 - 5_000_000 + 25_000_000 - 4_400_000 - 6_000_000
    assert (body["recurring_income_total"], body["recurring_expense_total"]) == (
        25_000_000,
        5_000_000,
    )
    assert body["goal_saving_total"] == 4_400_000
    assert body["overdue_recurring"] == []


def test_forecast_60_days_repeats_monthly_items(client, scenario):
    body = client.get(f"{FC}?days=60&start_date={OCT_1}").json()
    points = _points(body)
    assert len(points) == 60
    assert points["2026-11-01"]["delta_expense"] == 5_000_000
    assert points["2026-11-05"]["delta_income"] == 25_000_000
    assert points["2026-11-10"]["delta_goal_saving"] == 4_400_000
    assert body["goal_saving_total"] == 8_800_000


def test_case_7_low_balance_warning(client, scenario):
    _settings(client, starting_balance=0, starting_balance_on=OCT_1)
    body = client.get(f"{FC}?days=30&start_date={OCT_1}").json()
    assert body["low_balance_warning_day"] == OCT_1
    assert _points(body)[OCT_1]["projected_balance"] == -5_200_000
    assert body["min_balance"] == -5_800_000  # 04/10, trước khi nhận lương
    assert body["min_balance_day"] == "2026-10-04"


def test_actual_transactions_after_balance_date(client, cat, scenario):
    _tx(client, cat, "shopping", 1_000_000, "2026-10-02", note="Áo")
    body = client.get(f"{FC}?days=30&start_date={OCT_1}").json()
    points = _points(body)
    assert points["2026-10-02"]["delta_expense"] == 1_000_000
    assert points["2026-10-10"]["projected_balance"] == 24_600_000

    later = client.get(f"{FC}?days=30&start_date=2026-10-03").json()
    assert later["opening_balance"] == 11_000_000  # 12tr − 1tr giao dịch 02/10
    assert [o["name"] for o in later["overdue_recurring"]] == ["Tiền nhà"]
    assert _points(later)["2026-11-01"]["delta_expense"] == 5_000_000  # kỳ sau vẫn tính


def test_forecast_without_settings_or_history(client):
    body = client.get(f"{FC}?start_date={OCT_1}").json()
    assert body["days"] == 30
    assert (body["starting_balance_set"], body["starting_balance"]) == (False, 0)
    assert body["insufficient_history"] is True
    assert body["average_daily_variable_spending"] == 0
    assert body["low_balance_warning_day"] == OCT_1  # 0 < 1.000.000


@pytest.mark.parametrize("days", [0, 91, "abc"])
def test_forecast_validation(client, days):
    assert client.get(f"{FC}?days={days}").status_code == 422


def test_create_transaction_moves_forecast_item(client, scenario):
    rent_id = scenario["rent"]["id"]
    resp = client.post(f"{REC}/{rent_id}/create-transaction?today={OCT_1}", json={})
    assert resp.status_code == 201
    body = client.get(f"{FC}?days=30&start_date={OCT_1}").json()
    point = _points(body)[OCT_1]
    # Giao dịch thật thay cho kỳ định kỳ — không trừ 2 lần.
    assert point["delta_expense"] == 5_000_000
    assert point["events"] == []
    assert _points(body)["2026-10-10"]["projected_balance"] == 25_600_000


def test_calendar_month_icons(client, cat, scenario):
    _recurring(client, cat, "Internet", 300_000, "utilities", 5, "2026-10-05")
    resp = client.get(f"/api/v1/calendar/month?month=2026-10-01&today={OCT_1}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["month"] == OCT_1
    got = [(e["date"], e["icon"], e["kind"], e["amount"]) for e in body["events"]]
    assert got == [
        ("2026-10-01", "🏠", "recurring", 5_000_000),
        ("2026-10-05", "💰", "recurring", 25_000_000),
        ("2026-10-05", "📱", "recurring", 300_000),
        ("2026-10-10", "🎯", "goal_saving", 4_400_000),
    ]
    assert (body["income_total"], body["expense_total"], body["goal_saving_total"]) == (
        25_000_000,
        5_300_000,
        4_400_000,
    )
    assert not any(e["overdue"] for e in body["events"])


def test_calendar_after_create_transaction(client, cat, scenario):
    internet = _recurring(client, cat, "Internet", 300_000, "utilities", 5, "2026-10-05")
    tx = client.post(f"{REC}/{internet['id']}/create-transaction?today=2026-10-05", json={}).json()[
        "transaction"
    ]
    october = client.get("/api/v1/calendar/month?month=2026-10-01&today=2026-10-05").json()
    internet_events = [e for e in october["events"] if e["recurring_id"] == internet["id"]]
    assert [(e["kind"], e["transaction_id"]) for e in internet_events] == [("paid", tx["id"])]
    rent = next(e for e in october["events"] if e["icon"] == "🏠")
    assert rent["overdue"] is True  # 01/10 chưa ghi giao dịch
    november = client.get("/api/v1/calendar/month?month=2026-11-01&today=2026-10-05").json()
    assert ("2026-11-05", "📱") in [(e["date"], e["icon"]) for e in november["events"]]


def test_calendar_past_month_has_no_goal_saving(client, scenario):
    body = client.get("/api/v1/calendar/month?month=2026-09-01&today=2026-10-01").json()
    assert [e for e in body["events"] if e["kind"] == "goal_saving"] == []
