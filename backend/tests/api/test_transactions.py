import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Transaction

URL = "/api/v1/transactions"


@pytest.fixture
def make_tx(client, categories):
    def _make(slug: str, amount: int, occurred_on: str, **extra):
        category = categories[slug]
        payload = {
            "direction": category["kind"],
            "amount": amount,
            "occurred_on": occurred_on,
            "category_id": category["id"],
            **extra,
        }
        resp = client.post(URL, json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


# --- Tạo giao dịch (test case #1–#4) ---------------------------------------------------------


def test_create_expense_uses_category_default_spending_type(client, categories):
    """Test case #1."""
    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": 55000,
            "occurred_on": "2026-10-07",
            "category_id": categories["food"]["id"],
            "note": "Ăn phở",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["spending_type"] == "essential"
    assert body["amount"] == 55000
    assert body["source"] == "manual"
    assert body["category"]["slug"] == "food"
    assert body["note"] == "Ăn phở"


def test_create_expense_with_explicit_spending_type(make_tx):
    tx = make_tx("food", 450_000, "2026-10-07", spending_type="non_essential")

    assert tx["spending_type"] == "non_essential"


def test_income_with_spending_type_rejected(client, categories):
    """Test case #2."""
    resp = client.post(
        URL,
        json={
            "direction": "income",
            "amount": 25_000_000,
            "occurred_on": "2026-10-05",
            "category_id": categories["salary"]["id"],
            "spending_type": "essential",
        },
    )

    assert resp.status_code == 422


def test_income_has_null_spending_type(make_tx):
    tx = make_tx("salary", 25_000_000, "2026-10-05")

    assert tx["direction"] == "income"
    assert tx["spending_type"] is None


def test_category_kind_mismatch_rejected(client, categories):
    """Test case #3."""
    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": 55000,
            "occurred_on": "2026-10-07",
            "category_id": categories["salary"]["id"],
        },
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "category_kind_mismatch"


@pytest.mark.parametrize("amount", [0, -55000, 55000.5, "55000", 10**16])
def test_invalid_amount_rejected(client, categories, amount):
    """Test case #4 (+ số lẻ, chuỗi, quá lớn)."""
    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": amount,
            "occurred_on": "2026-10-07",
            "category_id": categories["food"]["id"],
        },
    )

    assert resp.status_code == 422


def test_unknown_category_rejected(client):
    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": 1000,
            "occurred_on": "2026-10-07",
            "category_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "category_not_found"


def test_archived_category_rejected_for_new_transaction(client, categories):
    client.patch(f"/api/v1/categories/{categories['other']['id']}", json={"is_archived": True})

    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": 1000,
            "occurred_on": "2026-10-07",
            "category_id": categories["other"]["id"],
        },
    )

    assert resp.status_code == 422
    assert resp.json()["code"] == "category_archived"


def test_blank_note_stored_as_null(make_tx):
    assert make_tx("food", 1000, "2026-10-07", note="   ")["note"] is None


def test_unknown_field_rejected(client, categories):
    resp = client.post(
        URL,
        json={
            "direction": "expense",
            "amount": 1000,
            "occurred_on": "2026-10-07",
            "category_id": categories["food"]["id"],
            "user_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert resp.status_code == 422


# --- Đọc / lọc / phân trang (test case #5) ------------------------------------------------------


def test_filter_by_date_range(client, make_tx):
    """Test case #5."""
    make_tx("food", 50_000, "2026-09-01")
    make_tx("transport", 30_000, "2026-09-15")
    make_tx("salary", 25_000_000, "2026-09-30")
    make_tx("food", 70_000, "2026-10-01")

    resp = client.get(URL, params={"from": "2026-09-01", "to": "2026-09-30"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [t["occurred_on"] for t in body["items"]] == ["2026-09-30", "2026-09-15", "2026-09-01"]


def test_filters_category_spending_type_direction_and_q(client, make_tx, categories):
    make_tx("food", 55_000, "2026-09-02", note="Ăn phở bò")
    make_tx("food", 300_000, "2026-09-03", note="Lẩu với bạn", spending_type="non_essential")
    make_tx("entertainment", 260_000, "2026-09-04", note="Netflix 100%_off")
    make_tx("salary", 25_000_000, "2026-09-05", note="Lương tháng 9")
    month = {"from": "2026-09-01", "to": "2026-09-30"}

    def notes(**params):
        return [t["note"] for t in client.get(URL, params={**month, **params}).json()["items"]]

    assert notes(category_id=categories["food"]["id"]) == ["Lẩu với bạn", "Ăn phở bò"]
    assert notes(spending_type="non_essential") == ["Netflix 100%_off", "Lẩu với bạn"]
    assert notes(direction="income") == ["Lương tháng 9"]
    assert notes(q="PHỞ") == ["Ăn phở bò"]
    assert notes(q="100%_") == ["Netflix 100%_off"]
    assert notes(q="%") == ["Netflix 100%_off"]


def test_pagination(client, make_tx):
    for day in range(1, 6):
        make_tx("food", 10_000 * day, f"2026-08-{day:02d}")
    params = {"from": "2026-08-01", "to": "2026-08-31", "page_size": 2}

    page1 = client.get(URL, params={**params, "page": 1}).json()
    page3 = client.get(URL, params={**params, "page": 3}).json()

    assert page1["total"] == 5
    assert [t["occurred_on"] for t in page1["items"]] == ["2026-08-05", "2026-08-04"]
    assert [t["occurred_on"] for t in page3["items"]] == ["2026-08-01"]
    assert page3["page"] == 3
    assert page3["page_size"] == 2


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-09-30", "to": "2026-09-01"},
        {"page": 0},
        {"page_size": 201},
        {"spending_type": "luxury"},
        {"from": "2026-13-01"},
    ],
)
def test_invalid_list_params(client, params):
    assert client.get(URL, params=params).status_code == 422


def test_get_by_id_and_404(client, make_tx):
    tx = make_tx("food", 55_000, "2026-10-07")

    assert client.get(f"{URL}/{tx['id']}").json()["id"] == tx["id"]
    missing = client.get(f"{URL}/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["code"] == "transaction_not_found"


# --- Sửa / xoá ------------------------------------------------------------------------------------


def test_patch_amount_keeps_other_fields(client, make_tx):
    tx = make_tx("food", 55_000, "2026-10-07", note="Ăn phở", spending_type="non_essential")

    resp = client.patch(f"{URL}/{tx['id']}", json={"amount": 60_000})

    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 60_000
    assert body["note"] == "Ăn phở"
    assert body["spending_type"] == "non_essential"
    assert body["updated_at"] >= tx["updated_at"]


def test_patch_category_without_spending_type_uses_new_default(client, make_tx, categories):
    tx = make_tx("food", 55_000, "2026-10-07")

    resp = client.patch(f"{URL}/{tx['id']}", json={"category_id": categories["shopping"]["id"]})

    assert resp.json()["category"]["slug"] == "shopping"
    assert resp.json()["spending_type"] == "non_essential"


def test_patch_expense_to_income_clears_spending_type(client, make_tx, categories):
    tx = make_tx("other", 500_000, "2026-10-07")

    resp = client.patch(
        f"{URL}/{tx['id']}",
        json={"direction": "income", "category_id": categories["other_income"]["id"]},
    )

    assert resp.status_code == 200
    assert resp.json()["direction"] == "income"
    assert resp.json()["spending_type"] is None


def test_patch_direction_without_matching_category_rejected(client, make_tx):
    tx = make_tx("food", 55_000, "2026-10-07")

    resp = client.patch(f"{URL}/{tx['id']}", json={"direction": "income"})

    assert resp.status_code == 422
    assert resp.json()["code"] == "category_kind_mismatch"


def test_patch_income_with_spending_type_rejected(client, make_tx):
    tx = make_tx("salary", 25_000_000, "2026-10-05")

    resp = client.patch(f"{URL}/{tx['id']}", json={"spending_type": "essential"})

    assert resp.status_code == 422
    assert resp.json()["code"] == "income_spending_type"


@pytest.mark.parametrize(
    "payload", [{"amount": None}, {"amount": 0}, {"occurred_on": None}, {"source": "nl"}]
)
def test_patch_invalid_payload(client, make_tx, payload):
    tx = make_tx("food", 55_000, "2026-10-07")

    assert client.patch(f"{URL}/{tx['id']}", json=payload).status_code == 422


def test_patch_keeps_archived_category_but_cannot_move_to_one(client, make_tx, categories):
    tx = make_tx("other", 100_000, "2026-10-07")
    client.patch(f"/api/v1/categories/{categories['other']['id']}", json={"is_archived": True})
    food_tx = make_tx("food", 50_000, "2026-10-07")

    same_category = client.patch(f"{URL}/{tx['id']}", json={"amount": 120_000})
    move_to_archived = client.patch(
        f"{URL}/{food_tx['id']}", json={"category_id": categories["other"]["id"]}
    )

    assert same_category.status_code == 200
    assert move_to_archived.status_code == 422
    assert move_to_archived.json()["code"] == "category_archived"


def test_delete(client, make_tx):
    tx = make_tx("food", 55_000, "2026-10-07")

    resp = client.delete(f"{URL}/{tx['id']}")

    assert resp.status_code == 204
    assert resp.content == b""
    assert client.get(f"{URL}/{tx['id']}").status_code == 404
    assert client.delete(f"{URL}/{tx['id']}").status_code == 404


# --- Tổng hợp (test case #6) ----------------------------------------------------------------------


def test_summary_matches_hand_calculation(client, make_tx, categories):
    """Test case #6."""
    make_tx("salary", 25_000_000, "2026-09-05")
    make_tx("freelance", 3_500_000, "2026-09-20")
    make_tx("housing", 6_000_000, "2026-09-01")
    make_tx("food", 55_000, "2026-09-02")
    make_tx("food", 450_000, "2026-09-12", spending_type="non_essential")
    make_tx("entertainment", 260_000, "2026-09-15")
    make_tx("electronics", 2_500_000, "2026-09-25", spending_type="irregular")
    make_tx("food", 999_999, "2026-10-01")  # ngoài kỳ

    resp = client.get(f"{URL}/summary", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["date_from"] == "2026-09-01"
    assert body["date_to"] == "2026-09-30"
    assert body["income_total"] == 28_500_000
    assert body["expense_total"] == 9_265_000
    assert body["net"] == 19_235_000
    assert body["by_spending_type"] == {
        "essential": 6_055_000,
        "non_essential": 710_000,
        "irregular": 2_500_000,
    }
    by_category = {c["category_id"]: c["total"] for c in body["by_category"]}
    assert by_category == {
        categories["salary"]["id"]: 25_000_000,
        categories["housing"]["id"]: 6_000_000,
        categories["freelance"]["id"]: 3_500_000,
        categories["electronics"]["id"]: 2_500_000,
        categories["food"]["id"]: 505_000,
        categories["entertainment"]["id"]: 260_000,
    }
    totals = [c["total"] for c in body["by_category"]]
    assert totals == sorted(totals, reverse=True)


def test_summary_respects_filters(client, make_tx):
    make_tx("salary", 25_000_000, "2026-09-05")
    make_tx("food", 55_000, "2026-09-02")
    make_tx("shopping", 400_000, "2026-09-03")

    body = client.get(
        f"{URL}/summary",
        params={"from": "2026-09-01", "to": "2026-09-30", "spending_type": "non_essential"},
    ).json()

    assert body["income_total"] == 0
    assert body["expense_total"] == 400_000
    assert body["net"] == -400_000


def test_summary_empty_period(client):
    body = client.get(f"{URL}/summary", params={"from": "1999-01-01", "to": "1999-01-31"}).json()

    assert body["income_total"] == 0
    assert body["expense_total"] == 0
    assert body["net"] == 0
    assert body["by_spending_type"] == {"essential": 0, "non_essential": 0, "irregular": 0}
    assert body["by_category"] == []


def test_db_rejects_inconsistent_rows(db, categories):
    """CHECK constraint ở DB là lớp bảo vệ cuối nếu service bị bỏ qua."""
    db.add(
        Transaction(
            direction="income",
            amount=1000,
            occurred_on=date(2026, 10, 1),
            category_id=uuid.UUID(categories["salary"]["id"]),
            spending_type="essential",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
