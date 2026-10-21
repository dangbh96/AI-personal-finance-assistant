"""API khoản định kỳ + phát hiện định kỳ (phase-12 § 6 test case 1, 8) — DB test thật, không AI."""

from datetime import date

import pytest

from app.models import RecurringTransaction, Transaction

TODAY = "2026-10-22"
Q = f"?today={TODAY}"
BASE = "/api/v1/recurring-transactions"


@pytest.fixture
def cat(categories) -> dict[str, str]:
    return {slug: c["id"] for slug, c in categories.items()}


def _create(client, cat, today=TODAY, expect=201, **overrides):
    body = {
        "name": "Internet",
        "direction": "expense",
        "amount": 300_000,
        "category_id": cat["utilities"],
        "frequency": "monthly",
        "day_of_month": 5,
    } | overrides
    resp = client.post(f"{BASE}?today={today}", json=body)
    assert resp.status_code == expect, resp.text
    return resp.json()


def _tx(client, category_id, amount, day, direction="expense", note=None, spending_type=None):
    body = {
        "direction": direction,
        "amount": amount,
        "occurred_on": day,
        "category_id": category_id,
        "note": note,
    }
    if spending_type:
        body["spending_type"] = spending_type
    resp = client.post("/api/v1/transactions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------- CRUD ----------


def test_create_monthly_defaults_next_due_after_today(client, cat):
    item = _create(client, cat)
    assert item["next_due_on"] == "2026-11-05"  # 05/10 <= hôm nay → kỳ sau
    assert item["spending_type"] == "essential"  # default của danh mục utilities
    assert item["icon"] == "📱"
    assert item["active"] is True and item["auto_detected"] is False
    assert item["due_status"] == "upcoming" and item["days_until_due"] == 14
    assert item["transaction_count"] == 0
    assert item["category"]["slug"] == "utilities"

    rent = _create(
        client, cat, name="Tiền nhà", amount=5_000_000, category_id=cat["housing"], day_of_month=31
    )
    assert rent["next_due_on"] == "2026-10-31"
    assert rent["icon"] == "🏠"


def test_create_infers_day_from_next_due_on(client, cat):
    salary = _create(
        client,
        cat,
        name="Lương",
        direction="income",
        amount=25_000_000,
        category_id=cat["salary"],
        day_of_month=None,
        next_due_on="2026-11-05",
    )
    assert salary["day_of_month"] == 5
    assert salary["spending_type"] is None
    assert salary["icon"] == "💰"

    weekly = _create(
        client,
        cat,
        name="Đi chợ",
        amount=500_000,
        category_id=cat["food"],
        frequency="weekly",
        day_of_month=None,
        day_of_week=1,
    )
    assert weekly["next_due_on"] == "2026-10-26"
    assert weekly["day_of_month"] is None

    yearly = _create(
        client,
        cat,
        name="Bảo hiểm xe",
        amount=600_000,
        category_id=cat["transport"],
        frequency="yearly",
        day_of_month=None,
        next_due_on="2027-02-28",
    )
    assert (yearly["day_of_month"], yearly["next_due_on"]) == (28, "2027-02-28")


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"frequency": "weekly", "day_of_month": 5}, "invalid_schedule"),
        ({"frequency": "weekly", "day_of_month": None}, "invalid_schedule"),
        ({"day_of_month": None}, "invalid_schedule"),
        ({"frequency": "yearly"}, "invalid_schedule"),
        ({"day_of_week": 1}, "invalid_schedule"),
        ({"next_due_on": "2026-11-06"}, "next_due_on_mismatch"),
        ({"direction": "income"}, "category_kind_mismatch"),
        (
            {"direction": "income", "spending_type": "irregular", "slug": "salary"},
            "income_spending_type",
        ),
    ],
)
def test_create_validation(client, cat, overrides, code):
    overrides = dict(overrides)
    slug = overrides.pop("slug", "utilities")
    resp = client.post(
        f"{BASE}{Q}",
        json={
            "name": "Internet",
            "direction": "expense",
            "amount": 300_000,
            "category_id": cat[slug],
            "frequency": "monthly",
            "day_of_month": 5,
        }
        | overrides,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == code


def test_create_rejects_bad_amount_and_extra_fields(client, cat):
    base = {
        "name": "Internet",
        "direction": "expense",
        "category_id": cat["utilities"],
        "frequency": "monthly",
        "day_of_month": 5,
    }
    assert client.post(BASE, json=base | {"amount": 0}).status_code == 422
    assert client.post(BASE, json=base | {"amount": 1.5}).status_code == 422
    assert client.post(BASE, json=base | {"amount": 1, "active": False}).status_code == 422
    assert client.post(BASE, json=base | {"amount": 1, "day_of_month": 32}).status_code == 422


def test_list_patch_pause_and_delete(client, cat, db):
    internet = _create(client, cat)
    rent = _create(
        client, cat, name="Tiền nhà", amount=5_000_000, category_id=cat["housing"], day_of_month=1
    )

    resp = client.patch(f"{BASE}/{internet['id']}{Q}", json={"amount": 350_000, "day_of_month": 10})
    assert resp.status_code == 200, resp.text
    assert (resp.json()["amount"], resp.json()["next_due_on"]) == (350_000, "2026-11-10")

    resp = client.patch(f"{BASE}/{internet['id']}{Q}", json={"active": False})
    assert resp.json()["active"] is False
    active = client.get(f"{BASE}?active=true&today={TODAY}").json()["items"]
    assert [i["id"] for i in active] == [rent["id"]]

    assert client.delete(f"{BASE}/{rent['id']}").status_code == 204
    assert db.get(RecurringTransaction, rent["id"]) is not None  # chỉ tắt, không xoá
    assert client.get(f"{BASE}?active=true").json()["items"] == []
    assert client.delete(f"{BASE}/00000000-0000-0000-0000-000000000000").status_code == 404


def test_list_sorted_by_next_due(client, cat):
    _create(client, cat)  # 05/11
    _create(
        client, cat, name="Tiền nhà", amount=5_000_000, category_id=cat["housing"], day_of_month=1
    )  # 01/11
    names = [i["name"] for i in client.get(f"{BASE}{Q}").json()["items"]]
    assert names == ["Tiền nhà", "Internet"]


def test_patch_frequency_and_reactivate_overdue(client, cat):
    item = _create(client, cat, next_due_on="2026-10-05")  # quá hạn, user nhập tay
    assert item["due_status"] == "overdue" and item["days_until_due"] == -17

    weekly = client.patch(
        f"{BASE}/{item['id']}{Q}", json={"frequency": "weekly", "day_of_week": 5}
    ).json()
    assert (weekly["day_of_month"], weekly["day_of_week"], weekly["next_due_on"]) == (
        None,
        5,
        "2026-10-23",
    )
    missing = client.patch(f"{BASE}/{item['id']}{Q}", json={"frequency": "monthly"})
    assert missing.status_code == 422
    assert missing.json()["code"] == "invalid_schedule"

    client.patch(f"{BASE}/{item['id']}{Q}", json={"active": False, "next_due_on": "2026-10-16"})
    resumed = client.patch(f"{BASE}/{item['id']}{Q}", json={"active": True}).json()
    assert resumed["active"] is True
    assert resumed["next_due_on"] == "2026-10-23"  # đã quá hạn → kỳ đầu tiên sau hôm nay


# ---------- tạo giao dịch từ khoản định kỳ ----------


def test_case_8_create_transaction_from_recurring(client, cat, db):
    internet = _create(client, cat, today="2026-10-01", next_due_on="2026-10-05")
    assert internet["next_due_on"] == "2026-10-05"

    resp = client.post(f"{BASE}/{internet['id']}/create-transaction?today=2026-10-05", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    tx = body["transaction"]
    assert tx["source"] == "recurring"
    assert tx["recurring_id"] == internet["id"]
    assert (tx["amount"], tx["occurred_on"], tx["note"]) == (300_000, "2026-10-05", "Internet")
    assert (tx["direction"], tx["spending_type"]) == ("expense", "essential")
    assert body["recurring"]["next_due_on"] == "2026-11-05"
    assert body["recurring"]["transaction_count"] == 1
    assert body["pyf_proposal"] is None

    stored = db.get(Transaction, tx["id"])
    assert (stored.source, str(stored.recurring_id)) == ("recurring", internet["id"])
    listed = client.get("/api/v1/transactions?from=2026-10-05&to=2026-10-05").json()["items"]
    assert [t["recurring_id"] for t in listed] == [internet["id"]]


def test_create_transaction_defaults_and_overrides(client, cat):
    item = _create(client, cat, next_due_on="2026-10-05")  # quá hạn so với 22/10
    resp = client.post(f"{BASE}/{item['id']}/create-transaction{Q}", json={})
    assert resp.json()["transaction"]["occurred_on"] == "2026-10-05"  # min(hạn, hôm nay)
    assert resp.json()["recurring"]["next_due_on"] == "2026-11-05"  # chỉ tiến 1 kỳ

    # Trả sớm kỳ 05/11 hôm nay với số tiền khác.
    resp = client.post(f"{BASE}/{item['id']}/create-transaction{Q}", json={"amount": 320_000})
    body = resp.json()
    assert (body["transaction"]["occurred_on"], body["transaction"]["amount"]) == (
        TODAY,
        320_000,
    )
    assert body["recurring"]["next_due_on"] == "2026-12-05"
    assert body["recurring"]["amount"] == 300_000


def test_create_transaction_inactive_conflict(client, cat):
    item = _create(client, cat)
    client.delete(f"{BASE}/{item['id']}")
    resp = client.post(f"{BASE}/{item['id']}/create-transaction{Q}", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "recurring_inactive"
    missing = client.post(
        f"{BASE}/00000000-0000-0000-0000-000000000000/create-transaction", json={}
    )
    assert missing.status_code == 404


def test_create_income_transaction_returns_pyf_proposal(client, cat):
    goal = client.post(
        f"/api/v1/goals{Q}",
        json={"name": "Laptop", "target_amount": 30_000_000, "deadline": "2027-03-22"},
    )
    assert goal.status_code == 201
    salary = _create(
        client,
        cat,
        name="Lương",
        direction="income",
        amount=25_000_000,
        category_id=cat["salary"],
        next_due_on="2026-10-05",
    )
    body = client.post(f"{BASE}/{salary['id']}/create-transaction{Q}", json={}).json()
    proposal = body["pyf_proposal"]
    assert proposal is not None
    assert proposal["income_transaction_id"] == body["transaction"]["id"]
    assert proposal["items"][0]["proposed_amount"] == 6_000_000  # 30tr / 5 tháng


# ---------- phát hiện ----------


def _rent_history(client, cat):
    return [
        _tx(client, cat["housing"], 5_000_000, day, note="Tiền nhà")
        for day in ("2026-07-31", "2026-08-31", "2026-09-30")
    ]


def test_case_1_detect_suggests_without_creating(client, cat, db):
    _rent_history(client, cat)
    _tx(client, cat["food"], 45_000, "2026-09-02", note="Phở")
    resp = client.post(f"{BASE}/detect{Q}", json={"from_date": "2026-07-01", "to_date": TODAY})
    assert resp.status_code == 200, resp.text
    [s] = resp.json()["suggestions"]
    assert (s["frequency"], s["amount"], s["day_of_month"]) == ("monthly", 5_000_000, 31)
    assert s["confidence"] >= 0.75 and s["confidence"] == 1.0
    assert (s["name"], s["icon"], s["occurrences"]) == ("Tiền nhà", "🏠", 3)
    assert s["next_due_on"] == "2026-10-31"
    assert db.query(RecurringTransaction).count() == 0  # chỉ đề xuất

    stored = client.get(f"{BASE}/suggestions").json()
    assert [x["id"] for x in stored["suggestions"]] == [s["id"]]


def test_confirm_suggestion_creates_and_links(client, cat, db):
    txs = _rent_history(client, cat)
    [s] = client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"]
    resp = client.post(f"{BASE}/suggestions/{s['id']}/confirm{Q}", json={"name": "Thuê nhà Q3"})
    assert resp.status_code == 201, resp.text
    recurring = resp.json()
    assert recurring["auto_detected"] is True
    assert (recurring["name"], recurring["amount"], recurring["day_of_month"]) == (
        "Thuê nhà Q3",
        5_000_000,
        31,
    )
    assert recurring["next_due_on"] == "2026-10-31"
    assert recurring["transaction_count"] == 3
    for tx in txs:
        assert str(db.get(Transaction, tx["id"]).recurring_id) == recurring["id"]

    assert client.get(f"{BASE}/suggestions").json()["suggestions"] == []
    again = client.post(f"{BASE}/suggestions/{s['id']}/confirm{Q}", json={})
    assert again.status_code == 404
    assert again.json()["code"] == "suggestion_not_found"
    # Giao dịch đã gắn → không phát hiện lại.
    assert client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"] == []


def test_detect_skips_pattern_covered_by_manual_recurring(client, cat):
    _rent_history(client, cat)
    _create(
        client, cat, name="Tiền nhà", amount=5_200_000, category_id=cat["housing"], day_of_month=1
    )
    assert client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"] == []


def test_dismiss_suggestion_is_remembered(client, cat, db):
    _rent_history(client, cat)
    [s] = client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"]
    assert client.post(f"{BASE}/suggestions/{s['id']}/dismiss").status_code == 204
    assert client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"] == []
    assert db.query(RecurringTransaction).count() == 0
    assert client.post(f"{BASE}/suggestions/{s['id']}/dismiss").status_code == 404


def test_confirm_with_invalid_next_due_on(client, cat, db):
    _rent_history(client, cat)
    [s] = client.post(f"{BASE}/detect{Q}", json={}).json()["suggestions"]
    resp = client.post(
        f"{BASE}/suggestions/{s['id']}/confirm{Q}", json={"next_due_on": "2026-11-15"}
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "next_due_on_mismatch"
    assert db.query(RecurringTransaction).count() == 0
    # Đề xuất vẫn còn để thử lại.
    assert len(client.get(f"{BASE}/suggestions").json()["suggestions"]) == 1


def test_detect_validates_range(client):
    resp = client.post(f"{BASE}/detect", json={"from_date": "2026-10-10", "to_date": "2026-10-01"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_date_range"
    resp = client.post(f"{BASE}/detect", json={"from_date": "2023-01-01", "to_date": TODAY})
    assert resp.status_code == 422


def test_detect_default_window_and_dates(client, cat):
    body = client.post(f"{BASE}/detect{Q}", json={}).json()
    assert (body["from_date"], body["to_date"]) == (str(date(2026, 4, 25)), TODAY)
