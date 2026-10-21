"""API Weekly review (Phase 6): generate (graph + fallback), get/list, reflection, pending.

OpenAI luôn được giả lập (`fake_ai`) hoặc tắt (`is_configured = False`) — không gọi mạng.
"""

import json
from datetime import date

import pytest

from app.ai import openai_client
from tests import review_dataset
from tests.review_dataset import DINNERS, WEEK_1, WEEK_2

URL = "/api/v1/reviews/weekly"
TODAY = "2026-10-20"

GOOD = {
    "observation": "Tuần này bạn chi 2.242.000 ₫, cao hơn tuần trước 18% (1.900.000 ₫).",
    "explanation": "Phần lớn mức tăng đến từ Ăn uống: 1.180.000 ₫, tăng 18%.",
    "notice": ["4 lần ăn tối, tổng 620.000 ₫."],
    "action": "Nếu bạn muốn, bạn có thể cân nhắc đặt giới hạn cho các bữa tối bên ngoài.",
    "reflection_question": "Có khoản nào trong tuần này bạn thấy không đáng tiền không?",
    "tone": "neutral",
}
INVENTED = {**GOOD, "notice": ["Bạn đã chi 999.000 ₫ cho cà phê."]}


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch):
    """Mặc định coi như chưa cấu hình AI (dev có thể có key thật); `fake_ai` bật lại."""
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)


@pytest.fixture
def seeded(db):
    return review_dataset.seed(db)


def _generate(client, week_start=WEEK_2, **body):
    return client.post(URL, json={"week_start": str(week_start), "today": TODAY, **body})


def _by_note(transactions, note):
    return [t for t in transactions if t.note == note]


# ---------- generate ----------


def test_generate_with_ai_persists_metrics_and_narrative(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(GOOD, ensure_ascii=False))

    resp = _generate(client)
    assert resp.status_code == 200, resp.text
    review = resp.json()
    assert review["week_start"] == "2026-10-12"
    assert review["week_end"] == "2026-10-18"
    assert review["status"] == "generated"
    assert review["model"] == openai_client.model_smart()
    assert review["reflections"] == []

    m = review["metrics"]
    assert (m["income"], m["expense"], m["previous_expense"]) == (0, 2_242_000, 1_900_000)
    assert m["expense_change_pct"] == 18
    assert m["by_spending_type"] == {
        "essential": 1_420_000,
        "non_essential": 672_000,
        "irregular": 150_000,
    }
    h = m["highlights"]
    assert (h["top_increase"]["slug"], h["top_increase"]["change_pct"]) == ("food", 18)
    cluster = h["repeated_clusters"][0]
    assert (cluster["label"], cluster["count"], cluster["total"]) == (
        "Ăn uống buổi tối",
        4,
        620_000,
    )

    n = review["narrative"]
    assert n["observation"] == GOOD["observation"]
    assert (n["fallback_used"], n["fallback_reason"]) == (False, None)

    assert len(calls) == 1
    assert calls[0]["model"] == openai_client.model_smart()
    system = calls[0]["messages"][0]["content"]
    assert "2242000" in system and "620.000" in system  # metrics JSON + số được phép


def test_generate_again_returns_existing_without_calling_ai(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(GOOD, ensure_ascii=False))
    first = _generate(client).json()

    again = _generate(client, regenerate=False)
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert again.json()["narrative"] == first["narrative"]
    assert len(calls) == 1


def test_ai_not_configured_uses_fallback(client, seeded):
    resp = _generate(client)
    assert resp.status_code == 200
    review = resp.json()
    assert review["model"] == "fallback_template"
    n = review["narrative"]
    assert (n["fallback_used"], n["fallback_reason"]) == (True, "AI_NOT_CONFIGURED")
    assert "2.242.000 ₫" in n["observation"] and "18%" in n["observation"]
    assert n["notice"][0] == "4 khoản “Ăn uống buổi tối”, tổng 620.000 ₫."


def test_invented_number_retries_then_succeeds(client, seeded, fake_ai):
    calls, responses = fake_ai
    responses += [json.dumps(INVENTED, ensure_ascii=False), json.dumps(GOOD, ensure_ascii=False)]

    review = _generate(client).json()
    assert review["narrative"]["fallback_used"] is False
    assert review["narrative"]["notice"] == GOOD["notice"]
    assert len(calls) == 2
    feedback = calls[1]["messages"][-1]["content"]
    assert "999.000" in feedback and "không có trong metrics" in feedback


def test_invalid_narrative_after_two_retries_falls_back(client, seeded, fake_ai):
    calls, responses = fake_ai
    banned = {**GOOD, "explanation": "Bạn tiêu quá nhiều cho ăn uống."}
    responses += [json.dumps(x, ensure_ascii=False) for x in (INVENTED, banned, INVENTED)]

    review = _generate(client).json()
    assert len(calls) == 3  # lần đầu + 2 lần retry
    n = review["narrative"]
    assert (n["fallback_used"], n["fallback_reason"]) == (True, "validation_failed")
    assert review["model"] == "fallback_template"
    assert "999.000" not in json.dumps(n, ensure_ascii=False)


def test_ai_error_falls_back_without_retry(client, seeded, monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    calls = []

    def _timeout(**kwargs):
        calls.append(kwargs)
        raise openai_client.AIUnavailable("AI_TIMEOUT", "timeout")

    monkeypatch.setattr(openai_client, "_chat_json", _timeout)
    review = _generate(client).json()
    assert len(calls) == 1
    assert review["narrative"]["fallback_reason"] == "AI_TIMEOUT"


def test_generate_empty_week(client):
    review = _generate(client).json()
    assert review["metrics"]["expense"] == 0
    assert review["narrative"]["observation"].endswith("chưa có giao dịch nào được ghi.")
    assert review["narrative"]["action"] is None


def test_generate_current_week_is_partial(client, seeded):
    review = _generate(client, today="2026-10-14").json()
    m = review["metrics"]
    assert (m["days_elapsed"], m["complete"], m["as_of"]) == (3, False, "2026-10-14")
    assert "tính đến 14/10" in review["narrative"]["observation"]


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"week_start": "2026-10-13"}, 422, "validation_error"),
        ({"week_start": "2026-10-26", "today": TODAY}, 422, "week_not_started"),
        ({"week_start": "2026-10-12", "extra": 1}, 422, "validation_error"),
    ],
)
def test_generate_rejects_invalid_week(client, body, status, code):
    resp = client.post(URL, json=body)
    assert resp.status_code == status
    assert resp.json()["code"] == code


# ---------- regenerate ----------


def test_regenerate_overwrites_narrative_and_keeps_reflections(client, db, seeded, fake_ai):
    calls, responses = fake_ai
    responses.append(json.dumps(GOOD, ensure_ascii=False))
    review = _generate(client).json()
    dinner = _by_note(seeded, "Đặt đồ ăn tối")[0]
    client.post(
        f"{URL}/{review['id']}/reflections",
        json={"answer": "Đặt đồ ăn muộn", "flagged_transaction_ids": [str(dinner.id)]},
    )

    review_dataset.seed(db, (review_dataset.Item(date(2026, 10, 18), "food", 90_000, "Bún bò"),))
    regen = {
        **GOOD,
        "observation": "Tuần này bạn chi 2.332.000 ₫, cao hơn tuần trước (1.900.000 ₫).",
        "explanation": "Phần lớn mức tăng đến từ Ăn uống.",
        "tone": "supportive",
    }
    responses.append(json.dumps(regen, ensure_ascii=False))
    regenerated = _generate(client, regenerate=True).json()

    assert regenerated["id"] == review["id"]
    assert regenerated["status"] == "generated"
    assert regenerated["metrics"]["expense"] == 2_332_000
    assert regenerated["narrative"]["tone"] == "supportive"
    assert len(regenerated["reflections"]) == 1
    assert len(calls) == 2


# ---------- get / list ----------


def test_get_by_week_404_then_200(client, seeded):
    missing = client.get(f"{URL}/2026-10-12")
    assert missing.status_code == 404
    assert missing.json()["code"] == "weekly_review_not_found"

    created = _generate(client).json()
    got = client.get(f"{URL}/2026-10-12")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


def test_list_filters_by_week_start(client, seeded):
    _generate(client, WEEK_1)
    _generate(client, WEEK_2)

    all_items = client.get(URL).json()["items"]
    assert [r["week_start"] for r in all_items][:2] == ["2026-10-12", "2026-10-05"]

    only_second = client.get(URL, params={"from": "2026-10-06", "to": "2026-10-31"}).json()
    assert [r["week_start"] for r in only_second["items"]] == ["2026-10-12"]

    bad = client.get(URL, params={"from": "2026-10-31", "to": "2026-10-01"})
    assert bad.status_code == 422


# ---------- reflection ----------


def test_reflection_marks_review_completed(client, seeded):
    review = _generate(client).json()
    orders = _by_note(seeded, "Đặt đồ ăn tối")
    assert len(orders) == 2

    resp = client.post(
        f"{URL}/{review['id']}/reflections",
        json={
            "answer": "  Không đáng tiền vì đặt lúc muộn  ",
            "flagged_transaction_ids": [str(o.id) for o in orders] + [str(orders[0].id)],
        },
    )
    assert resp.status_code == 201, resp.text
    answer = resp.json()
    assert answer["answer"] == "Không đáng tiền vì đặt lúc muộn"
    assert answer["question"] == review["narrative"]["reflection_question"]
    assert answer["review_kind"] == "weekly"
    assert answer["flagged_transaction_ids"] == [str(o.id) for o in orders]

    got = client.get(f"{URL}/2026-10-12").json()
    assert got["status"] == "completed"
    assert [r["id"] for r in got["reflections"]] == [answer["id"]]


def test_reflection_with_transaction_outside_week_is_rejected(client, seeded):
    review = _generate(client).json()
    outside = _by_note(seeded, "Tiền điện")[0]  # 08/10 — tuần trước
    inside = _by_note(seeded, "Ăn tối lẩu")[0]

    resp = client.post(
        f"{URL}/{review['id']}/reflections",
        json={"answer": "x", "flagged_transaction_ids": [str(inside.id), str(outside.id)]},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "flagged_transaction_out_of_week"

    got = client.get(f"{URL}/2026-10-12").json()
    assert got["reflections"] == []
    assert got["status"] == "generated"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"answer": "   "}, "reflection_empty"),
        (
            {"answer": "x", "flagged_transaction_ids": ["00000000-0000-0000-0000-000000000001"]},
            "flagged_transaction_not_found",
        ),
    ],
)
def test_reflection_validation_errors(client, seeded, payload, code):
    review = _generate(client).json()
    resp = client.post(f"{URL}/{review['id']}/reflections", json=payload)
    assert resp.status_code == 422
    assert resp.json()["code"] == code


def test_reflection_rejects_income_transaction(client, db, seeded):
    salary = review_dataset.seed(
        db, (review_dataset.Item(date(2026, 10, 15), "salary", 5_000_000, "Lương", None),)
    )[0]
    review = _generate(client).json()
    resp = client.post(
        f"{URL}/{review['id']}/reflections",
        json={"answer": "x", "flagged_transaction_ids": [str(salary.id)]},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "flagged_transaction_not_expense"


def test_reflection_only_flagged_without_answer(client, seeded):
    review = _generate(client).json()
    dinner = _by_note(seeded, "Ăn tối nhà hàng")[0]
    resp = client.post(
        f"{URL}/{review['id']}/reflections", json={"flagged_transaction_ids": [str(dinner.id)]}
    )
    assert resp.status_code == 201
    assert resp.json()["answer"] == ""


def test_reflection_unknown_review_404(client):
    resp = client.post(
        f"{URL}/00000000-0000-0000-0000-000000000001/reflections", json={"answer": "x"}
    )
    assert resp.status_code == 404


# ---------- pending banner ----------


def _pending(client, today):
    resp = client.get(f"{URL}/pending", params={"today": today})
    assert resp.status_code == 200
    return resp.json()


def test_pending_on_monday_until_completed(client, seeded):
    pending = _pending(client, "2026-10-19")
    assert pending == {
        "has_pending": True,
        "week_start": "2026-10-12",
        "review_id": None,
        "review_status": None,
    }

    review = _generate(client, today="2026-10-19").json()
    generated = _pending(client, "2026-10-19")
    assert (generated["has_pending"], generated["review_status"]) == (True, "generated")
    assert generated["review_id"] == review["id"]

    client.post(f"{URL}/{review['id']}/reflections", json={"answer": "Ổn"})
    assert _pending(client, "2026-10-19")["has_pending"] is False


def test_pending_only_on_monday(client, seeded):
    tuesday = _pending(client, "2026-10-20")
    assert (tuesday["has_pending"], tuesday["week_start"]) == (False, "2026-10-12")


def test_pending_false_when_previous_week_empty(client, db):
    review_dataset.seed(db, DINNERS)  # chỉ có giao dịch tuần 12/10
    assert _pending(client, "2026-10-26")["has_pending"] is False  # tuần 19/10 trống
    assert _pending(client, "2026-10-19")["has_pending"] is True
