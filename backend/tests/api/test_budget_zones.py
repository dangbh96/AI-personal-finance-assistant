"""API Flexible budget zones (Phase 9): GET zones, PATCH zone, recalculate, zone trong status,
advisor dùng comfort_high, giữ / bỏ ngưỡng khi copy / sửa ngân sách.

Dữ liệu (ngân sách 10/2026, 50/30/20 theo danh mục + dòng nhóm savings):

| Danh mục  | Planned   | 07/2026                      | 08/2026   | 09/2026   | 01–14/10/2026 |
|-----------|-----------|------------------------------|-----------|-----------|---------------|
| Ăn uống   | 4.000.000 | 3.800.000                    | 4.200.000 | 4.000.000 | 3.200.000     |
| Mua sắm   | 2.000.000 | 1.800.000 + Laptop 6.500.000 | 2.100.000 | 2.000.000 | 0             |
| Đi lại    | 1.000.000 | —                            | —         | —         | 300.000       |
| Giải trí  | 1.000.000 | —                            | —         | —         | 1.300.000     |
"""

import uuid
from datetime import date

import pytest

from app.services import budget_service
from tests import advice_dataset, review_dataset
from tests.review_dataset import Item

BUDGETS = "/api/v1/budgets"
ALLOCATIONS = "/api/v1/budget-allocations"
MONTH_END = "2026-10-31"
MID_MONTH = "2026-10-15"


def _split(month: date, slug: str, total: int, piece: int, note: str) -> list[Item]:
    count, rest = divmod(total, piece)
    items = [Item(month.replace(day=1 + i % 14), slug, piece, note) for i in range(count)]
    if rest:
        items.append(Item(month.replace(day=14), slug, rest, note))
    return items


JUL, AUG, SEP, OCT = (date(2026, m, 1) for m in (7, 8, 9, 10))
ITEMS: tuple[Item, ...] = (
    *_split(JUL, "food", 3_800_000, 200_000, "Đi chợ"),
    *_split(AUG, "food", 4_200_000, 200_000, "Đi chợ"),
    *_split(SEP, "food", 4_000_000, 200_000, "Đi chợ"),
    *_split(OCT, "food", 3_200_000, 200_000, "Đi chợ"),
    Item(date(2026, 7, 10), "shopping", 1_800_000, "Quần áo", "non_essential"),
    Item(date(2026, 7, 20), "shopping", 6_500_000, "Laptop", "irregular"),
    Item(date(2026, 8, 10), "shopping", 2_100_000, "Giày", "non_essential"),
    Item(date(2026, 9, 10), "shopping", 2_000_000, "Túi", "non_essential"),
    *_split(OCT, "transport", 300_000, 100_000, "Xăng"),
    *_split(OCT, "entertainment", 1_300_000, 100_000, "Xem phim"),
)
ROWS = (
    ("food", "essential", 4_000_000),
    ("shopping", "wants", 2_000_000),
    ("transport", "essential", 1_000_000),
    ("entertainment", "wants", 1_000_000),
)


@pytest.fixture
def budget(client, categories, db):
    review_dataset.seed(db, ITEMS)
    resp = client.post(
        BUDGETS,
        json={
            "period_month": "2026-10-01",
            "strategy": "fifty_thirty_twenty",
            "expected_income": 25_000_000,
            "status": "active",
            "allocations": [
                {"group": group, "category_id": categories[slug]["id"], "planned_amount": planned}
                for slug, group, planned in ROWS
            ]
            + [{"group": "savings", "jar_name": "savings", "planned_amount": 5_000_000}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _alloc_id(budget: dict, key: str) -> str:
    for a in budget["allocations"]:
        if (a["category"] and a["category"]["slug"] == key) or a["jar_name"] == key:
            return a["id"]
    raise KeyError(key)


def _zones(client, budget: dict, today: str = MONTH_END) -> dict[str, dict]:
    resp = client.get(f"{BUDGETS}/{budget['id']}/zones", params={"today": today})
    assert resp.status_code == 200, resp.text
    return {
        (z["category"]["slug"] if z["category"] else z["jar_name"]): z for z in resp.json()["items"]
    }


def _recalculate(client, budget: dict, ids: list[str] | None = None, today: str = MONTH_END):
    return client.post(
        f"{BUDGETS}/{budget['id']}/zones/recalculate",
        params={"today": today},
        json={"allocation_ids": ids},
    )


def _thresholds(z: dict) -> tuple:
    return (z["comfort_low"], z["comfort_high"], z["warning_threshold"])


def _patch(client, budget: dict, key: str, body: dict):
    return client.patch(f"{ALLOCATIONS}/{_alloc_id(budget, key)}/zone", json=body)


def _manual(low: int, high: int, warning: int) -> dict:
    return {
        "zone_mode": "manual",
        "comfort_low": low,
        "comfort_high": high,
        "warning_threshold": warning,
    }


# ---------- GET trước khi tính ----------


def test_new_allocations_are_auto_and_not_calculated(client, budget):
    assert all((a["zone_mode"], a["comfort_high"]) == ("auto", None) for a in budget["allocations"])
    zones = _zones(client, budget)
    assert set(zones) == {"food", "shopping", "transport", "entertainment"}  # không có savings
    food = zones["food"]
    assert (food["calculated"], food["zone"], _thresholds(food)) == (False, None, (None,) * 3)
    # Auto detail vẫn cho biết ngưỡng sẽ tính ra.
    assert food["auto"]["basis"] == "history"
    assert food["auto"]["suggested"]["comfort_high"] == 4_081_650
    assert food["auto"]["stale"] is False


# ---------- recalculate (test case 1, 2, 3 + idempotent) ----------


def test_recalculate_auto_zones_from_history(client, budget):
    resp = _recalculate(client, budget)
    assert resp.status_code == 200, resp.text
    zones = {
        (z["category"]["slug"] if z["category"] else z["jar_name"]): z for z in resp.json()["items"]
    }

    food = zones["food"]
    assert _thresholds(food) == (3_500_000, 4_081_650, 4_400_000)
    assert (food["calculated"], food["zone"], food["actual"]) == (True, "normal", 3_200_000)
    assert food["auto"]["basis"] == "history"
    assert (food["auto"]["mean"], food["auto"]["std"], food["auto"]["history_months"]) == (
        4_000_000,
        163_299,
        3,
    )
    assert [h["month"] for h in food["auto"]["history"]][-3:] == [
        "2026-07-01",
        "2026-08-01",
        "2026-09-01",
    ]

    shopping = zones["shopping"]
    assert _thresholds(shopping) == (1_750_000, 2_029_028, 2_200_000)
    july = next(h for h in shopping["auto"]["history"] if h["month"] == "2026-07-01")
    assert (july["actual"], july["irregular_excluded"], july["used"]) == (
        1_800_000,
        6_500_000,
        True,
    )
    assert shopping["auto"]["mean"] == 1_966_667

    transport = zones["transport"]
    assert _thresholds(transport) == (875_000, 1_125_000, 1_250_000)
    assert (transport["auto"]["basis"], transport["auto"]["fallback_reason"]) == (
        "fallback",
        "insufficient_history",
    )

    entertainment = zones["entertainment"]
    # Không có lịch sử → % dự phòng; 1.300.000 > 1.250.000.
    assert (entertainment["zone"], entertainment["actual"]) == ("review_needed", 1_300_000)


def test_recalculate_is_idempotent(client, budget):
    first = _recalculate(client, budget).json()
    second = _recalculate(client, budget).json()
    assert first == second
    budget_after = client.get(f"{BUDGETS}/{budget['id']}").json()
    food = next(a for a in budget_after["allocations"] if a["id"] == _alloc_id(budget, "food"))
    assert (food["zone_mode"], food["comfort_high"]) == ("auto", 4_081_650)


def test_recalculate_selected_rows_skips_manual(client, budget):
    assert (
        _patch(client, budget, "entertainment", _manual(800_000, 1_200_000, 1_500_000)).status_code
        == 200
    )
    ids = [_alloc_id(budget, "food"), _alloc_id(budget, "entertainment")]
    resp = _recalculate(client, budget, ids)
    assert resp.status_code == 200, resp.text
    zones = _zones(client, budget)
    assert zones["food"]["calculated"] is True
    assert zones["shopping"]["calculated"] is False
    assert _thresholds(zones["entertainment"]) == (800_000, 1_200_000, 1_500_000)
    assert zones["entertainment"]["auto"] is None


def test_recalculate_errors(client, budget):
    other = "00000000-0000-0000-0000-000000000000"
    resp = _recalculate(client, budget, [other])
    assert (resp.status_code, resp.json()["code"]) == (404, "allocation_not_found")
    resp = _recalculate(client, budget, [_alloc_id(budget, "savings")])
    assert (resp.status_code, resp.json()["code"]) == (422, "allocation_not_tracked")
    resp = client.post(f"{BUDGETS}/{other}/zones/recalculate", json={"allocation_ids": None})
    assert (resp.status_code, resp.json()["code"]) == (404, "budget_not_found")
    # Không gửi body cũng được (mọi dòng auto).
    assert client.post(f"{BUDGETS}/{budget['id']}/zones/recalculate").status_code == 200


# ---------- PATCH manual / auto (test case 4, 5, 6) ----------


def test_case_4_manual_entertainment_attention(client, budget):
    resp = _patch(client, budget, "entertainment", _manual(800_000, 1_200_000, 1_500_000))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["zone_mode"], body["comfort_low"], body["comfort_high"]) == (
        "manual",
        800_000,
        1_200_000,
    )
    assert body["warning_threshold"] == 1_500_000
    zone = _zones(client, budget)["entertainment"]
    assert (zone["zone"], zone["zone_mode"], zone["auto"]) == ("attention", "manual", None)


def test_case_5_manual_invalid_thresholds_422(client, budget):
    resp = _patch(client, budget, "entertainment", _manual(1_300_000, 1_200_000, 1_500_000))
    assert (resp.status_code, resp.json()["code"]) == (422, "invalid_zone_thresholds")
    resp = _patch(client, budget, "entertainment", _manual(800_000, 1_600_000, 1_500_000))
    assert (resp.status_code, resp.json()["code"]) == (422, "invalid_zone_thresholds")
    resp = _patch(client, budget, "entertainment", {"zone_mode": "manual", "comfort_high": 1})
    assert (resp.status_code, resp.json()["code"]) == (422, "zone_thresholds_required")
    resp = _patch(client, budget, "entertainment", {**_manual(1, 2, 3), "comfort_low": -1})
    assert (resp.status_code, resp.json()["code"]) == (422, "validation_error")
    # Không lưu gì.
    zone = _zones(client, budget)["entertainment"]
    assert (zone["zone_mode"], zone["calculated"]) == ("auto", False)


def test_case_6_food_review_needed(client, budget, categories):
    resp = client.post(
        "/api/v1/transactions",
        json={
            "direction": "expense",
            "amount": 1_050_000,
            "occurred_on": "2026-10-20",
            "category_id": categories["food"]["id"],
            "spending_type": "essential",
        },
    )
    assert resp.status_code == 201
    assert (
        _patch(client, budget, "food", _manual(3_500_000, 4_100_000, 4_200_000)).status_code == 200
    )
    food = _zones(client, budget)["food"]
    assert (food["actual"], food["zone"]) == (4_250_000, "review_needed")


def test_switch_back_to_auto_recomputes(client, budget):
    _patch(client, budget, "food", _manual(3_500_000, 4_500_000, 5_000_000))
    resp = _patch(client, budget, "food", {"zone_mode": "auto"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["zone_mode"], body["comfort_low"], body["comfort_high"]) == (
        "auto",
        3_500_000,
        4_081_650,
    )
    assert body["warning_threshold"] == 4_400_000


def test_patch_errors(client, budget):
    resp = _patch(client, budget, "food", {"zone_mode": "auto", "comfort_high": 4_000_000})
    assert (resp.status_code, resp.json()["code"]) == (422, "zone_thresholds_not_allowed")
    resp = _patch(client, budget, "savings", _manual(1, 2, 3))
    assert (resp.status_code, resp.json()["code"]) == (422, "allocation_not_tracked")
    resp = client.patch(
        f"{ALLOCATIONS}/00000000-0000-0000-0000-000000000000/zone", json=_manual(1, 2, 3)
    )
    assert (resp.status_code, resp.json()["code"]) == (404, "allocation_not_found")
    resp = _patch(client, budget, "food", {"zone_mode": "fixed"})
    assert resp.status_code == 422
    resp = _patch(client, budget, "food", {**_manual(1, 2, 3), "planned_amount": 1})
    assert resp.status_code == 422


def test_closed_budget_cannot_change_zones(client, budget):
    assert client.patch(f"{BUDGETS}/{budget['id']}", json={"status": "closed"}).status_code == 200
    resp = _patch(client, budget, "food", _manual(1, 2, 3))
    assert (resp.status_code, resp.json()["code"]) == (409, "budget_closed")
    resp = _recalculate(client, budget)
    assert (resp.status_code, resp.json()["code"]) == (409, "budget_closed")
    # Vẫn đọc được.
    assert client.get(f"{BUDGETS}/{budget['id']}/zones").status_code == 200


# ---------- pro-rata (test case 7) + status ----------


def test_case_7_pro_rata_early_warning_mid_month(client, budget):
    _recalculate(client, budget, today=MID_MONTH)
    zones = _zones(client, budget, MID_MONTH)
    food = zones["food"]
    assert (food["actual"], food["expected_to_date"]) == (3_200_000, 1_935_484)
    assert (food["zone"], food["early_warning"]) == ("normal", True)
    assert food["early_warning_message"] == "Đã dùng 80% ngân sách khi mới qua 48,4% tháng"
    # Đi lại 300.000 / 1.000.000 (30%) khi qua 48,4% tháng → không cảnh báo.
    assert zones["transport"]["early_warning"] is False
    # Cuối tháng: không còn "cảnh báo sớm".
    assert _zones(client, budget, MONTH_END)["food"]["early_warning"] is False


def test_status_rows_include_zone(client, budget):
    _recalculate(client, budget)
    resp = client.get(f"{BUDGETS}/{budget['id']}/status", params={"today": MID_MONTH})
    assert resp.status_code == 200
    rows = {
        (a["category"]["slug"] if a["category"] else a["jar_name"]): a
        for a in resp.json()["allocations"]
    }
    assert rows["savings"]["zone"] is None
    assert rows["food"]["zone"]["zone"] == "normal"
    assert rows["food"]["zone"]["early_warning"] is True
    assert rows["entertainment"]["zone"]["zone"] == "review_needed"


# ---------- giữ / bỏ ngưỡng khi sửa ngân sách ----------


def _allocation_inputs(budget: dict, planned: dict[str, int] | None = None) -> list[dict]:
    planned = planned or {}
    rows = []
    for a in budget["allocations"]:
        key = a["category"]["slug"] if a["category"] else a["jar_name"]
        rows.append(
            {
                "group": a["group"],
                "category_id": a["category_id"],
                "jar_name": a["jar_name"],
                "planned_amount": planned.get(key, a["planned_amount"]),
            }
        )
    return rows


def test_patch_budget_keeps_manual_and_unchanged_auto_zone(client, budget):
    _recalculate(client, budget)
    _patch(client, budget, "entertainment", _manual(800_000, 1_200_000, 1_500_000))
    resp = client.patch(
        f"{BUDGETS}/{budget['id']}",
        json={"allocations": _allocation_inputs(budget, {"shopping": 2_500_000})},
    )
    assert resp.status_code == 200, resp.text
    after = {
        (a["category"]["slug"] if a["category"] else a["jar_name"]): a
        for a in resp.json()["allocations"]
    }
    assert (after["food"]["zone_mode"], after["food"]["comfort_high"]) == ("auto", 4_081_650)
    assert (after["entertainment"]["zone_mode"], after["entertainment"]["comfort_high"]) == (
        "manual",
        1_200_000,
    )
    # Planned đổi → cache auto bị bỏ, chờ tính lại.
    assert (after["shopping"]["zone_mode"], after["shopping"]["comfort_high"]) == ("auto", None)


def test_copy_budget_keeps_manual_zone_and_drops_auto_cache(client, budget):
    _recalculate(client, budget)
    _patch(client, budget, "entertainment", _manual(800_000, 1_200_000, 1_500_000))
    resp = client.post(f"{BUDGETS}/copy-from-previous", json={"to_month": "2026-11-01"})
    assert resp.status_code == 201, resp.text
    copied = {
        (a["category"]["slug"] if a["category"] else a["jar_name"]): a
        for a in resp.json()["allocations"]
    }
    assert _thresholds(copied["entertainment"]) == (800_000, 1_200_000, 1_500_000)
    assert copied["entertainment"]["zone_mode"] == "manual"
    assert (copied["food"]["zone_mode"], copied["food"]["comfort_high"]) == ("auto", None)


def test_set_allocation_planned_drops_auto_cache(client, budget, db):
    _recalculate(client, budget)
    _patch(client, budget, "entertainment", _manual(800_000, 1_200_000, 1_500_000))
    model = budget_service.get_budget(db, uuid.UUID(budget["id"]))
    food = next(a for a in model.allocations if a.category and a.category.slug == "food")
    ent = next(a for a in model.allocations if a.category and a.category.slug == "entertainment")
    budget_service.set_allocation_planned(db, model, food, 4_000_000)
    assert food.comfort_high == 4_081_650  # planned không đổi → giữ cache
    budget_service.set_allocation_planned(db, model, food, 4_500_000)
    assert (food.comfort_low, food.comfort_high, food.warning_threshold) == (None, None, None)
    budget_service.set_allocation_planned(db, model, ent, 1_100_000)
    assert ent.comfort_high == 1_200_000  # manual giữ nguyên


# ---------- advisor dùng comfort_high (test case 8) ----------


def test_case_8_advisor_uses_comfort_high(client, db, monkeypatch):
    from app.ai import openai_client

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    review_dataset.seed(db, advice_dataset.ITEMS)
    advice_budget = advice_dataset.create_budget(db)
    food = next(a for a in advice_budget.allocations if a.category and a.category.slug == "food")
    # Ăn uống tháng 10: planned 4.000.000, actual 4.500.000 — vùng an toàn tới 4.600.000.
    resp = client.patch(
        f"{ALLOCATIONS}/{food.id}/zone", json=_manual(3_500_000, 4_600_000, 5_000_000)
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(
        "/api/v1/budget/advice/generate",
        json={"month": "2026-10-01", "today": advice_dataset.TODAY},
    )
    assert resp.status_code == 200, resp.text
    by = {a["allocation_label"]: a for a in resp.json()["items"]}
    advice = by["Ăn uống"]
    assert advice["verdict"] == "on_track"
    e = advice["evidence"]
    assert (e["comfort_high"], e["comfort_high_used"], e["threshold_amount"], e["over_amount"]) == (
        4_600_000,
        True,
        4_600_000,
        0,
    )
    assert e["zone"] == {
        "zone_mode": "manual",
        "planned_amount": 4_000_000,
        "comfort_low": 3_500_000,
        "comfort_high": 4_600_000,
        "warning_threshold": 5_000_000,
        "actual_amount": 4_500_000,
        "zone": "normal",
        "early_warning": False,
    }
    # Dòng chưa có vùng vẫn so với planned như Phase 8.
    assert by["Mua sắm"]["verdict"] == "one_off"
    assert by["Mua sắm"]["evidence"]["zone"] is None
