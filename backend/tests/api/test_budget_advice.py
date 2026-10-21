"""API Budget adjustment advisor (Phase 8): generate / list / accept / dismiss / settings.

OpenAI luôn được giả lập (`fake_ai`) hoặc tắt (`is_configured = False`) — không gọi mạng.
Dữ liệu: `tests/advice_dataset` (08–10/2026, ngân sách tháng 10; 4 test case chuẩn).
"""

import json

import pytest

from app.ai import advice_writer, openai_client
from tests import advice_dataset, review_dataset
from tests.advice_dataset import NOVEMBER, OCTOBER, TODAY

URL = "/api/v1/budget/advice"

FOOD_AI = {
    "observation": "Ăn uống tháng 10/2026: thực chi 4.500.000 ₫, vượt 500.000 ₫ so với kế hoạch "
    "4.000.000 ₫.",
    "explanation": "3 tháng gần nhất đều vượt kế hoạch và khá ổn định: 4.400.000 ₫ / "
    "4.600.000 ₫ / 4.500.000 ₫ (hệ số biến thiên 1,8%).",
    "action": "Nếu bạn xác nhận, app sẽ đặt ngân sách Ăn uống tháng sau thành 4.500.000 ₫.",
    "tone": "neutral",
}


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch):
    """Mặc định coi như chưa cấu hình AI (dev có thể có key thật); `fake_ai` bật lại.
    Gọi model tuần tự để thứ tự response giả xác định."""
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    monkeypatch.setattr(advice_writer, "MAX_PARALLEL", 1)


@pytest.fixture
def seeded(db):
    review_dataset.seed(db, advice_dataset.ITEMS)
    return advice_dataset.create_budget(db)


def _generate(client, month="2026-10-01", **body):
    return client.post(f"{URL}/generate", json={"month": month, "today": TODAY, **body})


def _by_label(items):
    return {a["allocation_label"]: a for a in items}


def _allocation_id(budget, slug):
    return str(next(a.id for a in budget.allocations if a.category and a.category.slug == slug))


def _budget_of(client, month):
    resp = client.get("/api/v1/budgets", params={"from": month, "to": month})
    items = resp.json()["items"]
    return items[0] if items else None


def _planned(budget, slug):
    return next(
        a["planned_amount"]
        for a in budget["allocations"]
        if a["category"] and a["category"]["slug"] == slug
    )


# ---------- generate ----------


def test_generate_four_standard_cases_without_ai(client, seeded):
    resp = _generate(client)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [a["allocation_label"] for a in items] == ["Ăn uống", "Mua sắm", "Giải trí", "Đi lại"]
    by = _by_label(items)
    assert {k: v["verdict"] for k, v in by.items()} == {
        "Ăn uống": "adjust_budget",
        "Mua sắm": "one_off",
        "Giải trí": "adjust_behavior",
        "Đi lại": "on_track",
    }
    assert all(a["status"] == "open" and a["month"] == "2026-10-01" for a in items)

    food = by["Ăn uống"]["evidence"]
    assert food["proposed_planned_amount"] == 4_500_000
    assert [h["actual"] for h in food["history_actuals"]] == [4_400_000, 4_600_000, 4_500_000]
    assert (food["planned_amount"], food["actual_amount"], food["over_amount"]) == (
        4_000_000,
        4_500_000,
        500_000,
    )
    assert (food["cv_pct"], food["rule"], food["comfort_high_used"]) == (
        1.8,
        "stable_overspend",
        False,
    )

    shopping = by["Mua sắm"]["evidence"]
    assert shopping["proposed_planned_amount"] is None
    assert shopping["one_off_transaction"]["note"] == "Laptop"
    assert shopping["one_off_transaction"]["amount"] == 6_500_000
    assert shopping["rule"] == "one_off_irregular"

    entertainment = by["Giải trí"]["evidence"]
    assert [h["actual"] for h in entertainment["history_actuals"]] == [
        800_000,
        1_600_000,
        1_400_000,
    ]
    assert entertainment["all_over_planned"] is False

    # AI chưa cấu hình → template dự phòng; on_track luôn dùng template (không gọi AI).
    assert by["Ăn uống"]["model"] == "fallback_template"
    assert by["Ăn uống"]["narrative"]["fallback_reason"] == "AI_NOT_CONFIGURED"
    assert "4.500.000 ₫" in by["Ăn uống"]["explanation"]
    assert by["Đi lại"]["model"] == "template"
    assert by["Đi lại"]["narrative"]["generated_by"] == "template"
    assert by["Đi lại"]["narrative"]["fallback_reason"] is None
    assert "“Laptop” 6.500.000 ₫" in by["Mua sắm"]["explanation"]


def test_generate_with_ai_uses_fast_model_and_evidence_prompt(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(FOOD_AI, ensure_ascii=False))

    resp = _generate(client, allocation_id=_allocation_id(seeded, "food"))
    assert resp.status_code == 200, resp.text
    [advice] = resp.json()["items"]
    assert advice["verdict"] == "adjust_budget"
    assert advice["model"] == openai_client.model_fast()
    assert advice["narrative"]["generated_by"] == "ai"
    assert advice["narrative"]["observation"] == FOOD_AI["observation"]
    assert advice["explanation"].startswith(FOOD_AI["observation"])

    assert len(calls) == 1
    assert calls[0]["model"] == openai_client.model_fast()
    system = calls[0]["messages"][0]["content"]
    assert "`adjust_budget`" in system and "Budget có thể thấp hơn thực tế" in system
    assert "4.500.000" in system and "proposed_planned_amount" in system
    assert "transaction_id" not in system and "allocation_id" not in system


def test_invalid_ai_output_is_retried_once_then_falls_back(client, seeded, fake_ai):
    calls, responses = fake_ai
    invented = {**FOOD_AI, "explanation": "Bạn tiêu quá nhiều, vượt 1.234.000 ₫."}
    no_proposal = {**FOOD_AI, "explanation": "Ổn định.", "action": "Nếu bạn muốn, hãy xem lại."}
    responses += [json.dumps(x, ensure_ascii=False) for x in (invented, no_proposal)]

    [advice] = _generate(client, allocation_id=_allocation_id(seeded, "food")).json()["items"]
    assert len(calls) == 2
    # `messages` là cùng 1 list hội thoại: [system, user, output 1, phản hồi lỗi 1, …].
    feedback = calls[1]["messages"][3]["content"]
    assert "1.234.000" in feedback and "bạn tiêu quá nhiều" in feedback
    assert advice["model"] == "fallback_template"
    assert advice["narrative"]["fallback_reason"] == "AI_INVALID_OUTPUT"
    assert "1.234.000" not in advice["explanation"]


def test_generate_again_keeps_open_advice_unless_regenerate(client, seeded, fake_ai):
    calls, responses = fake_ai
    food_id = _allocation_id(seeded, "food")
    responses.append(json.dumps(FOOD_AI, ensure_ascii=False))
    first = _generate(client, allocation_id=food_id).json()["items"][0]

    again = _generate(client, allocation_id=food_id).json()["items"]
    assert [a["id"] for a in again] == [first["id"]]
    assert len(calls) == 1

    responses.append(json.dumps({**FOOD_AI, "tone": "supportive"}, ensure_ascii=False))
    regenerated = _generate(client, allocation_id=food_id, regenerate=True).json()["items"]
    assert [a["id"] for a in regenerated] == [first["id"]]
    assert regenerated[0]["narrative"]["tone"] == "supportive"
    assert len(calls) == 2


def test_generate_skips_savings_and_validates_month(client, seeded):
    savings_id = str(next(a.id for a in seeded.allocations if a.group == "savings"))
    resp = _generate(client, allocation_id=savings_id)
    assert (resp.status_code, resp.json()["code"]) == (422, "allocation_not_tracked")

    resp = _generate(client, allocation_id="00000000-0000-0000-0000-000000000000")
    assert (resp.status_code, resp.json()["code"]) == (404, "allocation_not_found")

    resp = _generate(client, month="2026-10-15")
    assert (resp.status_code, resp.json()["code"]) == (422, "validation_error")

    resp = _generate(client, month="2026-12-01")
    assert (resp.status_code, resp.json()["code"]) == (422, "month_not_started")

    resp = _generate(client, month="2026-09-01")
    assert (resp.status_code, resp.json()["code"]) == (404, "budget_not_found")


def test_generate_requires_tracked_budget(client, db):
    review_dataset.seed(db, advice_dataset.ITEMS)
    advice_dataset.create_budget(db, status="draft")
    resp = _generate(client)
    assert (resp.status_code, resp.json()["code"]) == (404, "budget_not_active")


def test_insufficient_history_is_adjust_behavior(client, db):
    # Chỉ có dữ liệu tháng 9 và 10 (test case 5): Ăn uống vượt nhưng chưa đủ 3 tháng.
    items = tuple(i for i in advice_dataset.ITEMS if i.day >= advice_dataset.SEPTEMBER)
    review_dataset.seed(db, items)
    advice_dataset.create_budget(db)
    by = _by_label(_generate(client).json()["items"])
    food = by["Ăn uống"]
    assert food["verdict"] == "adjust_behavior"
    assert food["evidence"]["rule"] == "insufficient_history"
    assert food["evidence"]["history_months"] == 2
    assert "Mới có 2 tháng có dữ liệu (cần 3 tháng)" in food["explanation"]


# ---------- list ----------


def test_list_filters_by_month_status_and_allocation(client, seeded):
    _generate(client)
    assert len(client.get(URL).json()["items"]) == 4
    assert len(client.get(URL, params={"month": "2026-10-20"}).json()["items"]) == 4
    assert client.get(URL, params={"month": "2026-09-01"}).json()["items"] == []
    food_id = _allocation_id(seeded, "food")
    [food] = client.get(URL, params={"allocation_id": food_id}).json()["items"]
    assert food["allocation_label"] == "Ăn uống"
    assert len(client.get(URL, params={"status": "open"}).json()["items"]) == 4
    resp = client.get(URL, params={"status": "closed"})
    assert (resp.status_code, resp.json()["code"]) == (422, "validation_error")


# ---------- accept ----------


def _advice(client, label):
    return _by_label(_generate(client).json()["items"])[label]


def test_accept_creates_next_month_draft_and_applies_proposed(client, seeded):
    """Test case 7: accept adjust_budget, tháng 11 chưa có budget → nháp copy + planned mới."""
    food = _advice(client, "Ăn uống")
    assert _budget_of(client, "2026-11-01") is None

    resp = client.post(
        f"{URL}/{food['id']}/accept", json={"confirm": True, "target_month": "2026-11-01"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["advice"]["status"] == "accepted"
    assert body["advice"]["applied_month"] == "2026-11-01"
    assert body["updated_allocation"]["planned_amount"] == 4_500_000
    assert body["updated_allocation"]["category"]["slug"] == "food"
    assert body["budget"] == {
        "id": body["budget"]["id"],
        "period_month": "2026-11-01",
        "status": "draft",
        "created": True,
    }

    november = _budget_of(client, "2026-11-01")
    assert november["status"] == "draft"
    assert _planned(november, "food") == 4_500_000
    assert _planned(november, "shopping") == 2_000_000
    assert november["savings_target"] == advice_dataset.SAVINGS_PLANNED
    # Ngân sách tháng 10 không đổi.
    assert _planned(_budget_of(client, "2026-10-01"), "food") == 4_000_000

    open_items = client.get(URL, params={"status": "open"}).json()["items"]
    assert food["id"] not in {a["id"] for a in open_items}


def test_accept_updates_existing_next_month_budget_in_place(client, seeded, db):
    november = advice_dataset.create_budget(db, NOVEMBER)
    food_row = next(a for a in november.allocations if a.category and a.category.slug == "food")
    food = _advice(client, "Ăn uống")

    body = client.post(f"{URL}/{food['id']}/accept", json={"confirm": True}).json()
    assert body["budget"]["created"] is False
    assert body["budget"]["status"] == "active"
    assert body["updated_allocation"]["id"] == str(food_row.id)
    assert _planned(_budget_of(client, "2026-11-01"), "food") == 4_500_000


def test_accept_adds_missing_line_to_next_month(client, seeded, db):
    inputs = [a for a in advice_dataset.allocation_inputs(db) if a.planned_amount != 4_000_000]
    advice_dataset.create_budget(db, NOVEMBER, allocations=inputs)
    food = _advice(client, "Ăn uống")
    body = client.post(f"{URL}/{food['id']}/accept", json={"confirm": True}).json()
    assert body["updated_allocation"]["planned_amount"] == 4_500_000
    november = _budget_of(client, "2026-11-01")
    assert _planned(november, "food") == 4_500_000
    assert november["allocations"][-1]["category"]["slug"] == "food"


def test_accept_requires_confirmation(client, seeded):
    """Test case 8: thiếu confirm → 422, budget không đổi, advice vẫn open."""
    food = _advice(client, "Ăn uống")
    for body in ({}, {"confirm": False, "target_month": "2026-11-01"}):
        resp = client.post(f"{URL}/{food['id']}/accept", json=body)
        assert (resp.status_code, resp.json()["code"]) == (422, "confirmation_required")
    assert _budget_of(client, "2026-11-01") is None
    [still_open] = client.get(URL, params={"allocation_id": food["budget_allocation_id"]}).json()[
        "items"
    ]
    assert still_open["status"] == "open"


def test_accept_rejects_non_adjust_budget_and_resolved_advice(client, seeded):
    advice = _by_label(_generate(client).json()["items"])
    resp = client.post(f"{URL}/{advice['Mua sắm']['id']}/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (422, "advice_not_adjustable")

    food_id = advice["Ăn uống"]["id"]
    resp = client.post(
        f"{URL}/{food_id}/accept", json={"confirm": True, "target_month": "2026-10-01"}
    )
    assert (resp.status_code, resp.json()["code"]) == (422, "invalid_target_month")
    resp = client.post(
        f"{URL}/{food_id}/accept", json={"confirm": True, "target_month": "2026-11-15"}
    )
    assert (resp.status_code, resp.json()["code"]) == (422, "validation_error")

    assert client.post(f"{URL}/{food_id}/accept", json={"confirm": True}).status_code == 200
    resp = client.post(f"{URL}/{food_id}/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (409, "advice_not_open")

    resp = client.post(f"{URL}/00000000-0000-0000-0000-000000000000/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (404, "advice_not_found")


def test_accept_over_income_needs_extra_confirmation(client, seeded, db):
    # Tháng 11: tổng planned 13.000.000 = thu nhập dự kiến → +500.000 sẽ vượt thu nhập.
    advice_dataset.create_budget(db, NOVEMBER, expected_income=13_000_000)
    food = _advice(client, "Ăn uống")
    resp = client.post(f"{URL}/{food['id']}/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (422, "planned_exceeds_income")
    assert _planned(_budget_of(client, "2026-11-01"), "food") == 4_000_000

    resp = client.post(
        f"{URL}/{food['id']}/accept", json={"confirm": True, "confirm_over_income": True}
    )
    assert resp.status_code == 200, resp.text
    assert _planned(_budget_of(client, "2026-11-01"), "food") == 4_500_000


def test_accept_into_closed_budget_conflicts(client, seeded, db):
    advice_dataset.create_budget(db, NOVEMBER)
    november = _budget_of(client, "2026-11-01")
    assert (
        client.patch(f"/api/v1/budgets/{november['id']}", json={"status": "closed"}).status_code
        == 200
    )
    food = _advice(client, "Ăn uống")
    resp = client.post(f"{URL}/{food['id']}/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (409, "budget_closed")
    [advice] = client.get(URL, params={"allocation_id": food["budget_allocation_id"]}).json()[
        "items"
    ]
    assert advice["status"] == "open"


# ---------- dismiss ----------


def test_dismiss_hides_from_open_and_is_not_regenerated(client, seeded):
    shopping = _advice(client, "Mua sắm")
    resp = client.post(
        f"{URL}/{shopping['id']}/dismiss", json={"reason": "  one-off already handled "}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["status"], resp.json()["dismiss_reason"]) == (
        "dismissed",
        "one-off already handled",
    )

    open_ids = {a["id"] for a in client.get(URL, params={"status": "open"}).json()["items"]}
    assert shopping["id"] not in open_ids and len(open_ids) == 3
    dismissed = client.get(URL, params={"status": "dismissed", "month": "2026-10-01"}).json()
    assert [a["id"] for a in dismissed["items"]] == [shopping["id"]]

    items = _generate(client, regenerate=True).json()["items"]
    shopping_items = [a for a in items if a["allocation_label"] == "Mua sắm"]
    assert [(a["id"], a["status"]) for a in shopping_items] == [(shopping["id"], "dismissed")]

    resp = client.post(f"{URL}/{shopping['id']}/dismiss", json={})
    assert (resp.status_code, resp.json()["code"]) == (409, "advice_not_open")
    resp = client.post(f"{URL}/{shopping['id']}/accept", json={"confirm": True})
    assert (resp.status_code, resp.json()["code"]) == (409, "advice_not_open")


def test_dismiss_without_reason(client, seeded):
    entertainment = _advice(client, "Giải trí")
    resp = client.post(f"{URL}/{entertainment['id']}/dismiss", json={})
    assert (resp.json()["status"], resp.json()["dismiss_reason"]) == ("dismissed", None)


# ---------- settings ----------


def test_settings_get_and_patch(client, seeded):
    resp = client.get(f"{URL}/settings")
    assert resp.json() == {
        "one_off_share_threshold": 0.6,
        "stable_cv_threshold": 0.15,
        "min_history_months": 3,
        "budget_rounding_step": 100_000,
    }

    resp = client.patch(f"{URL}/settings", json={"stable_cv_threshold": 0.01})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stable_cv_threshold"] == 0.01
    assert resp.json()["min_history_months"] == 3
    assert client.get(f"{URL}/settings").json()["stable_cv_threshold"] == 0.01

    # CV Ăn uống 1,8% > 1% → không còn "ổn định".
    food = _advice(client, "Ăn uống")
    assert food["verdict"] == "adjust_behavior"
    assert food["evidence"]["stable_cv_threshold_pct"] == 1.0

    for body in ({"stable_cv_threshold": 0}, {"min_history_months": 1}, {"unknown": 1}):
        resp = client.patch(f"{URL}/settings", json=body)
        assert (resp.status_code, resp.json()["code"]) == (422, "validation_error"), body


def test_settings_fall_back_to_defaults_for_bad_stored_values(client, db):
    from app.repositories import app_setting_repository

    app_setting_repository.set_value(
        db, "budget_advisor", {"one_off_share_threshold": 5, "min_history_months": 4}
    )
    assert client.get(f"{URL}/settings").json() == {
        "one_off_share_threshold": 0.6,
        "stable_cv_threshold": 0.15,
        "min_history_months": 4,
        "budget_rounding_step": 100_000,
    }


def test_deleting_draft_budget_removes_its_advice(client, db):
    review_dataset.seed(db, advice_dataset.ITEMS)
    budget = advice_dataset.create_budget(db)
    assert len(_generate(client).json()["items"]) == 4
    assert client.patch(f"/api/v1/budgets/{budget.id}", json={"status": "draft"}).status_code == 200
    assert client.delete(f"/api/v1/budgets/{budget.id}").status_code == 204
    assert client.get(URL, params={"month": OCTOBER.isoformat()}).json()["items"] == []
