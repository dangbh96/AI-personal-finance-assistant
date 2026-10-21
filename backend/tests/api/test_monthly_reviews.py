"""API Monthly review (Phase 7): generate (graph + fallback), get/list, metrics preview, reflection.

OpenAI luôn được giả lập (`fake_ai`) hoặc tắt (`is_configured = False`) — không gọi mạng.
Dữ liệu: `tests/monthly_dataset` (tháng 9 và 10/2026, ngân sách tháng 10).
"""

import json
from datetime import date

import pytest

from app.ai import openai_client
from tests import review_dataset
from tests.monthly_dataset import LAPTOP, OCT_DINNERS, OCT_ITEMS, SEP_ITEMS, create_october_budget
from tests.review_dataset import Item

URL = "/api/v1/reviews/monthly"
WEEKLY_URL = "/api/v1/reviews/weekly"
TODAY = "2026-11-02"

GOOD = {
    "observation": "Tháng 10/2026 bạn thu 25.000.000 ₫, chi 20.608.000 ₫, còn lại 4.392.000 ₫ "
    "(tỉ lệ tiết kiệm 17,6%). Chi tiêu cao hơn tháng trước 12%.",
    "explanation": "Phần lớn mức tăng đến từ khoản mua laptop 15.000.000 ₫, một khoản bất thường.",
    "notice": ["Ăn uống vượt ngân sách 500.000 ₫."],
    "action": "Nếu bạn muốn, bạn có thể xem phần tư vấn điều chỉnh ngân sách cho tháng tới.",
    "reflection_question": "Điều gì trong tháng này bạn muốn giữ cho tháng tới?",
    "tone": "neutral",
}
NO_DRIVER = {**GOOD, "explanation": "Chi tiêu tăng so với tháng trước."}


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch):
    """Mặc định coi như chưa cấu hình AI (dev có thể có key thật); `fake_ai` bật lại."""
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)


@pytest.fixture
def seeded(db):
    transactions = review_dataset.seed(db, SEP_ITEMS + OCT_ITEMS)
    create_october_budget(db)
    return transactions


def _generate(client, month="2026-10-01", **body):
    return client.post(URL, json={"month": month, "today": TODAY, **body})


def _by_note(transactions, note, day=None):
    return [t for t in transactions if t.note == note and (day is None or t.occurred_on == day)]


# ---------- generate ----------


def test_generate_with_ai_persists_monthly_metrics(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(GOOD, ensure_ascii=False))

    resp = _generate(client)
    assert resp.status_code == 200, resp.text
    review = resp.json()
    assert (review["month"], review["month_end"]) == ("2026-10-01", "2026-10-31")
    assert (review["status"], review["model"]) == ("generated", openai_client.model_smart())
    assert review["narrative"]["fallback_used"] is False

    m = review["metrics"]
    assert (m["period"], m["complete"]) == ("month", True)
    assert (m["income"], m["expense"], m["saved"]) == (25_000_000, 20_608_000, 4_392_000)
    assert m["savings_rate_pct"] == 17.6
    assert (m["previous_expense"], m["expense_change_pct"]) == (18_400_000, 12)
    assert (m["previous_saved"], m["previous_savings_rate_pct"]) == (6_600_000, 26.4)
    assert m["by_spending_type"] == {
        "essential": 4_448_000,
        "non_essential": 1_160_000,
        "irregular": 15_000_000,
    }
    assert m["spending_type_pct"] == {"essential": 21.6, "non_essential": 5.6, "irregular": 72.8}
    assert m["increase_driver"] == "irregular"
    laptop = m["irregular_items"][0]
    assert (laptop["note"], laptop["amount"], laptop["category_slug"]) == (
        "Laptop",
        15_000_000,
        "electronics",
    )

    budget = m["budget"]
    assert (budget["status"], budget["over_budget_count"]) == ("active", 1)
    food = next(line for line in budget["lines"] if line["label"] == "Ăn uống")
    assert (food["planned"], food["actual"], food["variance"]) == (4_000_000, 4_500_000, 500_000)
    assert food["status"] == "over_budget"
    assert [line["label"] for line in budget["over_lines"]] == ["Ăn uống"]
    assert budget["unbudgeted_actual"] == 15_000_000

    assert len(calls) == 1
    system = calls[0]["messages"][0]["content"]
    assert "review tháng" in system and "increase_driver" in system
    assert "15.000.000" in system and "17.6" in system
    assert "budget_id" not in system


def test_ai_not_configured_uses_monthly_fallback(client, seeded):
    review = _generate(client).json()
    assert review["model"] == "fallback_template"
    n = review["narrative"]
    assert (n["fallback_used"], n["fallback_reason"]) == (True, "AI_NOT_CONFIGURED")
    assert "cao hơn tháng trước 12%" in n["observation"]
    assert "“Laptop” 15.000.000 ₫" in n["explanation"]
    assert n["notice"][0].startswith("Ăn uống vượt ngân sách 500.000 ₫")


def test_missing_irregular_driver_retries_with_feedback(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses += [json.dumps(x, ensure_ascii=False) for x in (NO_DRIVER, GOOD)]

    review = _generate(client).json()
    assert review["narrative"]["fallback_used"] is False
    assert review["narrative"]["explanation"] == GOOD["explanation"]
    assert len(calls) == 2
    feedback = calls[1]["messages"][-1]["content"]
    assert "khoản bất thường" in feedback and "15.000.000" in feedback


def test_invalid_after_retries_falls_back(client, seeded, fake_ai):
    calls, responses = fake_ai
    invented = {**GOOD, "notice": ["Bạn có thể tiết kiệm thêm 20.000.000 ₫."]}
    verdict = {**GOOD, "action": "Nếu bạn muốn: ngân sách sai, hãy adjust_budget."}
    responses += [json.dumps(x, ensure_ascii=False) for x in (invented, verdict, NO_DRIVER)]

    review = _generate(client).json()
    assert len(calls) == 3
    n = review["narrative"]
    assert (n["fallback_used"], n["fallback_reason"]) == (True, "validation_failed")
    assert "20.000.000" not in json.dumps(n, ensure_ascii=False)


def test_generate_again_returns_existing_without_ai(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(GOOD, ensure_ascii=False))
    first = _generate(client).json()
    again = _generate(client)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert len(calls) == 1


def test_regenerate_keeps_reflections_and_recomputes(client, db, seeded):
    review = _generate(client).json()
    laptop = _by_note(seeded, "Laptop")[0]
    client.post(
        f"{URL}/{review['id']}/reflections",
        json={"answer": "Laptop dùng cho công việc", "flagged_transaction_ids": [str(laptop.id)]},
    )
    review_dataset.seed(db, (Item(date(2026, 10, 30), "food", 92_000, "Bún bò"),))

    regenerated = _generate(client, regenerate=True).json()
    assert regenerated["id"] == review["id"]
    assert regenerated["status"] == "generated"
    assert regenerated["metrics"]["expense"] == 20_700_000
    assert len(regenerated["reflections"]) == 1


def test_previous_month_without_spending(client, seeded):
    review = _generate(client, "2026-09-01").json()
    m = review["metrics"]
    assert (m["saved"], m["savings_rate_pct"]) == (6_600_000, 26.4)
    assert m["spending_type_pct"] == {"essential": 50.0, "non_essential": 33.2, "irregular": 16.8}
    assert (m["expense_change_pct"], m["increase_driver"], m["budget"]) == (None, None, None)
    assert "Tháng trước chưa có khoản chi nào để so sánh" in review["narrative"]["observation"]


def test_current_month_is_partial(client, seeded):
    review = _generate(client, today="2026-10-20").json()
    m = review["metrics"]
    assert (m["days_elapsed"], m["complete"], m["as_of"]) == (20, False, "2026-10-20")
    assert "tính đến 20/10" in review["narrative"]["observation"]


def test_draft_budget_is_not_included(client, db):
    review_dataset.seed(db, OCT_ITEMS)
    create_october_budget(db, status="draft")
    assert _generate(client).json()["metrics"]["budget"] is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"month": "2026-10-15"}, "validation_error"),
        ({"month": "2026-12-01", "today": TODAY}, "month_not_started"),
        ({"month": "2026-10-01", "extra": 1}, "validation_error"),
    ],
)
def test_generate_rejects_invalid_month(client, body, code):
    resp = client.post(URL, json=body)
    assert resp.status_code == 422
    assert resp.json()["code"] == code


# ---------- weekly reflections digest (test case 6) ----------


def _weekly_reflection(client, week_start, answer, flagged=()):
    review = client.post(WEEKLY_URL, json={"week_start": week_start, "today": TODAY}).json()
    resp = client.post(
        f"{WEEKLY_URL}/{review['id']}/reflections",
        json={"answer": answer, "flagged_transaction_ids": [str(t.id) for t in flagged]},
    )
    assert resp.status_code == 201, resp.text


def test_metrics_include_weekly_reflections_of_the_month(client, seeded):
    dinners = [_by_note(seeded, "Ăn tối nhà hàng", d.day)[0] for d in OCT_DINNERS]
    _weekly_reflection(client, "2026-09-28", "Tuần cuối tháng 9")  # Thứ Hai thuộc tháng 9
    _weekly_reflection(client, "2026-10-05", "Bữa tối hơi đắt", dinners[:1])
    _weekly_reflection(client, "2026-10-12", "Lại ăn tối ngoài", dinners[1:2])
    _weekly_reflection(client, "2026-10-19", "Đặt bàn vì tiện", dinners[2:3])
    _weekly_reflection(client, "2026-10-26", "Tuần này ổn")

    m = _generate(client).json()["metrics"]
    digest = m["weekly_reflections"]
    assert [d["week_start"] for d in digest] == [
        "2026-10-05",
        "2026-10-12",
        "2026-10-19",
        "2026-10-26",
    ]
    assert [d["answer"] for d in digest][0] == "Bữa tối hơi đắt"
    flagged_ids = [f["id"] for d in digest for f in d["flagged"]]
    assert flagged_ids == [str(t.id) for t in dinners]
    assert digest[0]["flagged"][0]["amount"] == 300_000
    assert (m["flagged_count"], m["flagged_total"]) == (3, 900_000)


# ---------- get / list / preview ----------


def test_get_by_month_404_then_200(client, seeded):
    missing = client.get(f"{URL}/2026-10-01")
    assert missing.status_code == 404
    assert missing.json()["code"] == "monthly_review_not_found"

    created = _generate(client).json()
    for month in ("2026-10-01", "2026-10-15"):
        got = client.get(f"{URL}/{month}")
        assert got.status_code == 200
        assert got.json()["id"] == created["id"]


def test_list_filters_by_month(client, seeded):
    _generate(client, "2026-09-01")
    _generate(client, "2026-10-01")
    items = client.get(URL).json()["items"]
    assert [r["month"] for r in items] == ["2026-10-01", "2026-09-01"]

    only_oct = client.get(URL, params={"from": "2026-10-01", "to": "2026-12-01"}).json()
    assert [r["month"] for r in only_oct["items"]] == ["2026-10-01"]
    assert client.get(URL, params={"from": "2026-12-01", "to": "2026-09-01"}).status_code == 422


def test_metrics_preview_does_not_persist(client, seeded, fake_ai):
    calls, _ = fake_ai
    resp = client.get(f"{URL}/2026-10-01/metrics", params={"today": TODAY})
    assert resp.status_code == 200
    m = resp.json()
    assert (m["expense_change_pct"], m["savings_rate_pct"]) == (12, 17.6)
    assert m["highlights"]["top_transactions"][0]["note"] == "Laptop"
    assert m["budget"]["over_lines"][0]["variance"] == 500_000
    assert calls == []
    assert client.get(f"{URL}/2026-10-01").status_code == 404


# ---------- monthly reflection (test case 7) ----------


def test_monthly_reflection_marks_completed(client, seeded):
    review = _generate(client).json()
    laptop = _by_note(seeded, LAPTOP.note)[0]
    resp = client.post(
        f"{URL}/{review['id']}/reflections",
        json={
            "answer": "  Giữ mức ăn uống, laptop là khoản một lần  ",
            "flagged_transaction_ids": [str(laptop.id), str(laptop.id)],
        },
    )
    assert resp.status_code == 201, resp.text
    answer = resp.json()
    assert answer["review_kind"] == "monthly"
    assert answer["answer"] == "Giữ mức ăn uống, laptop là khoản một lần"
    assert answer["question"] == review["narrative"]["reflection_question"]
    assert answer["flagged_transaction_ids"] == [str(laptop.id)]

    got = client.get(f"{URL}/2026-10-01").json()
    assert got["status"] == "completed"
    assert [r["id"] for r in got["reflections"]] == [answer["id"]]


def test_monthly_reflection_rejects_transaction_outside_month(client, seeded):
    review = _generate(client).json()
    september = _by_note(seeded, "Khám răng")[0]
    resp = client.post(
        f"{URL}/{review['id']}/reflections",
        json={"answer": "x", "flagged_transaction_ids": [str(september.id)]},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "flagged_transaction_out_of_month"
    got = client.get(f"{URL}/2026-10-01").json()
    assert (got["status"], got["reflections"]) == ("generated", [])


@pytest.mark.parametrize(
    ("note", "payload", "code"),
    [
        (None, {"answer": "  "}, "reflection_empty"),
        ("Lương tháng 10", None, "flagged_transaction_not_expense"),
    ],
)
def test_monthly_reflection_validation(client, seeded, note, payload, code):
    review = _generate(client).json()
    if payload is None:
        income = _by_note(seeded, note)[0]
        payload = {"answer": "x", "flagged_transaction_ids": [str(income.id)]}
    resp = client.post(f"{URL}/{review['id']}/reflections", json=payload)
    assert resp.status_code == 422
    assert resp.json()["code"] == code


def test_monthly_reflection_unknown_review_404(client):
    resp = client.post(
        f"{URL}/00000000-0000-0000-0000-000000000001/reflections", json={"answer": "x"}
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "monthly_review_not_found"


def test_weekly_review_id_is_not_a_monthly_review(client, seeded):
    weekly = client.post(WEEKLY_URL, json={"week_start": "2026-10-05", "today": TODAY}).json()
    resp = client.post(f"{URL}/{weekly['id']}/reflections", json={"answer": "x"})
    assert resp.status_code == 404
