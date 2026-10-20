"""API /budgets (Phase 4) — test case mục 6 của phase-04 + validate/CRUD."""

import pytest

URL = "/api/v1/budgets"
INCOME = 25_000_000


def _preview(client, **body):
    body = {"period_month": "2026-10-01", "expected_income": INCOME, **body}
    return client.post(f"{URL}/preview", json=body)


def _create(client, *, strategy="envelope", month="2026-10-01", status="draft", **extra):
    preview = _preview(
        client, strategy=strategy, period_month=month, savings_target=extra.pop("savings", None)
    )
    assert preview.status_code == 200, preview.text
    allocations = [
        {k: a[k] for k in ("group", "category_id", "jar_name", "planned_amount")}
        for a in preview.json()["budget"]["allocations"]
    ]
    body = {
        "period_month": month,
        "strategy": strategy,
        "expected_income": INCOME,
        "status": status,
        "allocations": allocations,
        **extra,
    }
    return client.post(URL, json=body)


def _by_jar(budget: dict) -> dict[str, int]:
    return {a["jar_name"]: a["planned_amount"] for a in budget["allocations"]}


def _code(resp) -> str:
    return resp.json()["code"]


# ---------- test case mục 6 ----------


def test_period_month_must_be_first_day(client):
    resp = _preview(client, strategy="envelope", period_month="2026-10-15")
    assert resp.status_code == 422
    assert _code(resp) == "validation_error"

    resp = client.post(
        URL,
        json={
            "period_month": "2026-10-15",
            "strategy": "envelope",
            "expected_income": INCOME,
            "allocations": [{"group": "savings", "jar_name": "Saving", "planned_amount": 1}],
        },
    )
    assert resp.status_code == 422


def test_second_budget_same_month_conflict(client):
    assert _create(client, status="active").status_code == 201
    resp = _create(client, status="active")
    assert resp.status_code == 409
    assert _code(resp) == "budget_exists"


def test_envelope_preview_25m(client):
    resp = _preview(client, strategy="envelope")
    assert resp.status_code == 200
    data = resp.json()
    assert _by_jar(data["budget"]) == {
        "Essential": 13_000_000,
        "Fun": 3_000_000,
        "Shopping": 2_000_000,
        "Saving": 5_000_000,
        "Unexpected": 2_000_000,
    }
    assert data["budget"]["savings_target"] == 5_000_000
    assert data["budget"]["totals"]["planned_total"] == INCOME
    assert data["budget"]["totals"]["unallocated"] == 0
    assert data["warnings"] == []


def test_fifty_thirty_twenty_preview_25m(client):
    data = _preview(client, strategy="fifty_thirty_twenty").json()
    assert _by_jar(data["budget"]) == {
        "essential": 12_500_000,
        "wants": 7_500_000,
        "savings": 5_000_000,
    }
    ref = data["reference_50_30_20"]
    assert (ref["essential"], ref["wants"], ref["savings"]) == (12_500_000, 7_500_000, 5_000_000)
    assert all(c["difference"] == 0 for c in ref["comparison"])


def test_pyf_preview_25m(client):
    data = _preview(client, strategy="pyf", savings_target=5_000_000).json()
    budget = data["budget"]
    assert budget["allocations"][0]["group"] == "savings"
    assert _by_jar(budget) == {
        "savings": 5_000_000,
        "essential": 12_000_000,
        "wants": 6_000_000,
        "irregular": 2_000_000,
    }
    assert budget["savings_target"] == 5_000_000
    assert budget["totals"]["planned_total"] - budget["totals"]["by_group"]["savings"] == 20_000_000


def test_pyf_savings_target_exceeds_income(client):
    resp = _preview(client, strategy="pyf", savings_target=30_000_000)
    assert resp.status_code == 422
    assert _code(resp) == "savings_target_exceeds_income"


def test_pyf_requires_savings_target(client):
    resp = _preview(client, strategy="pyf")
    assert resp.status_code == 422
    assert _code(resp) == "savings_target_required"


def test_copy_from_previous_month(client):
    sep = _create(client, month="2026-09-01", status="active").json()
    patched = client.patch(
        f"{URL}/{sep['id']}",
        json={
            "allocations": [
                {**a, "planned_amount": 2_500_000} if a["jar_name"] == "Fun" else a
                for a in (
                    {k: x[k] for k in ("group", "category_id", "jar_name", "planned_amount")}
                    for x in sep["allocations"]
                )
            ]
        },
    )
    assert patched.status_code == 200, patched.text

    resp = client.post(f"{URL}/copy-from-previous", json={"to_month": "2026-10-01"})
    assert resp.status_code == 201, resp.text
    oct_ = resp.json()
    assert oct_["period_month"] == "2026-10-01"
    assert oct_["status"] == "draft"
    assert oct_["strategy"] == "envelope"
    assert oct_["expected_income"] == INCOME
    assert _by_jar(oct_) == _by_jar(patched.json())
    assert _by_jar(oct_)["Fun"] == 2_500_000
    assert [a["jar_name"] for a in oct_["allocations"]] == [
        a["jar_name"] for a in sep["allocations"]
    ]
    assert {a["id"] for a in oct_["allocations"]}.isdisjoint({a["id"] for a in sep["allocations"]})


def test_allocation_without_category_or_jar(client):
    resp = _preview(
        client,
        strategy="envelope",
        allocations=[{"group": "essential", "planned_amount": 1_000_000}],
    )
    assert resp.status_code == 422
    assert _code(resp) == "validation_error"


def test_custom_budget_exceeds_income_warning(client):
    allocations = [
        {"group": "essential", "jar_name": "Essential", "planned_amount": 15_000_000},
        {"group": "wants", "jar_name": "Fun", "planned_amount": 3_000_000},
        {"group": "wants", "jar_name": "Shopping", "planned_amount": 2_000_000},
        {"group": "savings", "jar_name": "Saving", "planned_amount": 5_000_000},
        {"group": "irregular", "jar_name": "Unexpected", "planned_amount": 2_000_000},
    ]
    data = _preview(client, strategy="envelope", allocations=allocations).json()
    assert data["budget"]["totals"]["planned_total"] == 27_000_000
    assert data["budget"]["totals"]["unallocated"] == -2_000_000
    warning = next(w for w in data["warnings"] if w["code"] == "planned_exceeds_income")
    assert warning["amount"] == 2_000_000

    body = {
        "period_month": "2026-10-01",
        "strategy": "envelope",
        "expected_income": INCOME,
        "allocations": allocations,
    }
    resp = client.post(URL, json=body)
    assert resp.status_code == 422
    assert _code(resp) == "planned_exceeds_income"

    resp = client.post(URL, json={**body, "confirm_over_income": True})
    assert resp.status_code == 201
    assert resp.json()["totals"]["planned_total"] == 27_000_000


# ---------- CRUD ----------


def test_create_get_list(client):
    created = _create(client, strategy="pyf", savings=5_000_000)
    assert created.status_code == 201, created.text
    budget = created.json()
    assert budget["status"] == "draft"
    assert budget["savings_target"] == 5_000_000
    assert [a["position"] for a in budget["allocations"]] == [0, 1, 2, 3]
    assert budget["reference_50_30_20"]["comparison"][0]["difference"] == -500_000

    got = client.get(f"{URL}/{budget['id']}")
    assert got.status_code == 200
    assert got.json() == budget

    _create(client, month="2026-11-01")
    items = client.get(URL, params={"from": "2026-10-01", "to": "2026-10-01"}).json()["items"]
    assert [b["id"] for b in items] == [budget["id"]]
    months = [b["period_month"] for b in client.get(URL).json()["items"]]
    assert months[:2] == ["2026-11-01", "2026-10-01"]

    assert client.get(URL, params={"from": "2026-11-01", "to": "2026-10-01"}).status_code == 422


def test_get_unknown_budget(client):
    resp = client.get(f"{URL}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert _code(resp) == "budget_not_found"


def test_edit_amount_then_reopen(client):
    budget = _create(client).json()
    allocations = [
        {k: a[k] for k in ("group", "category_id", "jar_name", "planned_amount")}
        for a in budget["allocations"]
    ]
    for a in allocations:
        if a["jar_name"] == "Fun":
            a["planned_amount"] = 2_500_000
    resp = client.patch(f"{URL}/{budget['id']}", json={"allocations": allocations})
    assert resp.status_code == 200
    reopened = client.get(f"{URL}/{budget['id']}").json()
    assert _by_jar(reopened)["Fun"] == 2_500_000
    assert reopened["totals"]["unallocated"] == 500_000
    assert len(reopened["allocations"]) == 5


def test_status_transitions(client):
    budget = _create(client).json()
    url = f"{URL}/{budget['id']}"
    assert client.patch(url, json={"status": "closed"}).status_code == 422
    resp = client.patch(url, json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    assert _code(client.delete(url)) == "budget_not_draft"

    assert client.patch(url, json={"status": "closed"}).json()["status"] == "closed"
    resp = client.patch(url, json={"expected_income": 30_000_000})
    assert resp.status_code == 409
    assert _code(resp) == "budget_closed"
    assert client.patch(url, json={"status": "active"}).status_code == 200


def test_patch_income_checks_over_income(client):
    budget = _create(client).json()
    url = f"{URL}/{budget['id']}"
    resp = client.patch(url, json={"expected_income": 20_000_000})
    assert resp.status_code == 422
    assert _code(resp) == "planned_exceeds_income"
    resp = client.patch(url, json={"expected_income": 20_000_000, "confirm_over_income": True})
    assert resp.status_code == 200
    assert resp.json()["totals"]["unallocated"] == -5_000_000


@pytest.mark.parametrize(
    "body",
    [
        {"status": None},
        {"expected_income": None},
        {"strategy": "pyf"},
        {"period_month": "2026-12-01"},
        {"allocations": []},
    ],
)
def test_patch_rejects_invalid_fields(client, body):
    budget = _create(client).json()
    assert client.patch(f"{URL}/{budget['id']}", json=body).status_code == 422


def test_delete_draft(client):
    budget = _create(client).json()
    assert client.delete(f"{URL}/{budget['id']}").status_code == 204
    assert client.get(f"{URL}/{budget['id']}").status_code == 404
    assert _create(client).status_code == 201  # tháng đã trống lại


def test_create_closed_rejected(client):
    resp = _create(client, status="closed")
    assert resp.status_code == 422
    assert _code(resp) == "invalid_status"


# ---------- validate phân bổ ----------


def test_unknown_jar(client):
    resp = _preview(
        client,
        strategy="envelope",
        allocations=[{"group": "wants", "jar_name": "Du lịch", "planned_amount": 1_000_000}],
    )
    assert resp.status_code == 422
    assert _code(resp) == "unknown_jar"


def test_group_row_must_match_group(client):
    resp = _preview(
        client,
        strategy="fifty_thirty_twenty",
        allocations=[{"group": "wants", "jar_name": "Essential", "planned_amount": 1}],
    )
    assert _code(resp) == "invalid_group_row"


def test_duplicate_rows(client, categories):
    food = categories["food"]["id"]
    resp = _preview(
        client,
        strategy="envelope",
        allocations=[
            {"group": "essential", "category_id": food, "planned_amount": 1},
            {"group": "essential", "category_id": food, "planned_amount": 2},
        ],
    )
    assert _code(resp) == "duplicate_allocation"


def test_jar_and_category_overlap(client, categories):
    resp = _preview(
        client,
        strategy="envelope",
        allocations=[
            {"group": "essential", "jar_name": "Essential", "planned_amount": 10_000_000},
            {"group": "essential", "category_id": categories["food"]["id"], "planned_amount": 1},
        ],
    )
    assert resp.status_code == 422
    assert _code(resp) == "overlapping_allocations"
    assert "Ăn uống" in resp.json()["detail"]


def test_group_and_category_rows_overlap(client, categories):
    resp = _preview(
        client,
        strategy="fifty_thirty_twenty",
        allocations=[
            {"group": "essential", "jar_name": "essential", "planned_amount": 10_000_000},
            {"group": "wants", "category_id": categories["shopping"]["id"], "planned_amount": 1},
        ],
    )
    assert _code(resp) == "overlapping_allocations"


def test_pyf_savings_row_with_category_rows(client, categories):
    """PYF: savings trước + phân bổ theo danh mục — savings không khớp chi tiêu nên không trùng."""
    allocations = [
        {"group": "savings", "jar_name": "savings", "planned_amount": 5_000_000},
        {
            "group": "essential",
            "category_id": categories["food"]["id"],
            "planned_amount": 4_000_000,
        },
        {
            "group": "wants",
            "category_id": categories["shopping"]["id"],
            "planned_amount": 2_000_000,
        },
    ]
    data = _preview(client, strategy="pyf", allocations=allocations).json()
    assert data["budget"]["totals"]["planned_total"] == 11_000_000
    assert data["budget"]["allocations"][1]["category"]["slug"] == "food"
    assert data["budget"]["savings_target"] == 5_000_000


@pytest.mark.parametrize("slug", ["salary", "archived"])
def test_category_row_must_be_active_expense(client, categories, slug):
    if slug == "archived":
        created = client.post(
            "/api/v1/categories",
            json={"name": "Thú cưng", "kind": "expense", "default_spending_type": "essential"},
        ).json()
        client.patch(f"/api/v1/categories/{created['id']}", json={"is_archived": True})
        category_id, code = created["id"], "category_archived"
    else:
        category_id, code = categories[slug]["id"], "category_kind_mismatch"
    resp = _preview(
        client,
        strategy="envelope",
        allocations=[{"group": "essential", "category_id": category_id, "planned_amount": 1}],
    )
    assert _code(resp) == code


def test_preview_warns_existing_budget(client):
    _create(client)
    codes = [w["code"] for w in _preview(client, strategy="envelope").json()["warnings"]]
    assert codes == ["budget_exists"]


def test_envelope_warns_category_not_in_jar(client):
    client.post(
        "/api/v1/categories",
        json={"name": "Thú cưng", "kind": "expense", "default_spending_type": "essential"},
    )
    warnings = _preview(client, strategy="envelope").json()["warnings"]
    warning = next(w for w in warnings if w["code"] == "categories_not_in_jar")
    assert "Thú cưng" in warning["message"]


def test_list_jars(client):
    items = client.get(f"{URL}/jars").json()["items"]
    assert [j["name"] for j in items] == ["Essential", "Fun", "Shopping", "Saving", "Unexpected"]
    essential = items[0]
    assert essential["group"] == "essential"
    assert essential["default_percent"] == 52
    assert {c["slug"] for c in essential["categories"]} == {
        "housing",
        "food",
        "transport",
        "utilities",
        "health",
        "education",
    }
    assert items[3]["categories"] == []


# ---------- copy ----------


def test_copy_errors(client):
    resp = client.post(f"{URL}/copy-from-previous", json={"to_month": "2026-10-01"})
    assert resp.status_code == 404
    assert _code(resp) == "budget_not_found"

    _create(client, month="2026-09-01")
    _create(client, month="2026-10-01")
    resp = client.post(f"{URL}/copy-from-previous", json={"to_month": "2026-10-01"})
    assert resp.status_code == 409

    resp = client.post(
        f"{URL}/copy-from-previous", json={"from_month": "2026-09-01", "to_month": "2026-09-01"}
    )
    assert _code(resp) == "same_month"
    resp = client.post(f"{URL}/copy-from-previous", json={"to_month": "2026-12-15"})
    assert resp.status_code == 422


def test_copy_explicit_month_skips_archived_category(client, categories):
    pet = client.post(
        "/api/v1/categories",
        json={"name": "Thú cưng", "kind": "expense", "default_spending_type": "essential"},
    ).json()
    body = {
        "period_month": "2026-07-01",
        "strategy": "pyf",
        "expected_income": INCOME,
        "allocations": [
            {"group": "savings", "jar_name": "savings", "planned_amount": 5_000_000},
            {"group": "essential", "category_id": pet["id"], "planned_amount": 500_000},
            {"group": "essential", "category_id": categories["food"]["id"], "planned_amount": 1},
        ],
    }
    assert client.post(URL, json=body).status_code == 201
    client.patch(f"/api/v1/categories/{pet['id']}", json={"is_archived": True})

    resp = client.post(
        f"{URL}/copy-from-previous", json={"from_month": "2026-07-01", "to_month": "2026-10-01"}
    )
    assert resp.status_code == 201
    rows = resp.json()["allocations"]
    assert [a["jar_name"] or a["category"]["slug"] for a in rows] == ["savings", "food"]
    assert [a["position"] for a in rows] == [0, 1]
