"""Classification memory (Phase 3): CRUD preference, học từ correction, exact shortcut, few-shot.

OpenAI được giả lập (fixture `fake_ai`) — không cần API key.
"""

import json

import pytest
from sqlalchemy import select

from app.ai import openai_client
from app.models import ClassificationFeedback, ClassificationPreference

TX_URL = "/api/v1/transactions"
PARSE_URL = f"{TX_URL}/parse"
PREF_URL = "/api/v1/classification-preferences"
TODAY = "2026-10-07"


def _draft(**overrides) -> dict:
    return {
        "direction": "expense",
        "amount": 1_800_000,
        "occurred_on": TODAY,
        "note": "Mua giày MLB",
        "category_slug": "shopping",
        "spending_type": "non_essential",
        "confidence": 0.85,
        "reason": "Mua sắm quần áo giày dép",
        **overrides,
    }


def _output(*drafts: dict) -> str:
    return json.dumps({"transactions": list(drafts), "warnings": []})


def _parse(client, text: str) -> dict:
    resp = client.post(PARSE_URL, json={"text": text, "today": TODAY})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _save(client, parsed: dict, index: int = 0, **final) -> dict:
    """Lưu draft thứ `index` như frontend: giá trị cuối (có thể đã sửa) + ai_suggestion gốc."""
    draft = parsed["drafts"][index]
    payload = {
        "direction": draft["direction"],
        "amount": draft["amount"],
        "occurred_on": draft["occurred_on"],
        "category_id": draft["category_id"],
        "spending_type": draft["spending_type"],
        "note": draft["note"],
        "source": "nl",
        "raw_input": parsed["raw_input"],
        "ai_suggestion": {**draft, "model": parsed["model"]},
        **final,
    }
    resp = client.post(TX_URL, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_pref(client, pattern="giày", category_slug="shopping", spending_type="essential"):
    resp = client.post(
        PREF_URL,
        json={
            "pattern": pattern,
            "category_slug": category_slug,
            "spending_type": spending_type,
            "example_text": f"Tao coi {pattern} là thiết yếu",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _prefs(client) -> list[dict]:
    resp = client.get(PREF_URL)
    assert resp.status_code == 200
    return resp.json()["items"]


@pytest.fixture
def no_ai(monkeypatch):
    """AI chưa cấu hình và mọi lời gọi OpenAI đều bị coi là lỗi."""

    def _must_not_call(**_):
        raise AssertionError("không được gọi OpenAI")

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    monkeypatch.setattr(openai_client, "_chat_json", _must_not_call)


# ---------- exact shortcut ----------


def test_exact_preference_shortcut_without_openai(client, categories, no_ai):
    """Test case #3: có preference `giay` → "Mua giày Nike 2tr" không gọi OpenAI."""
    pref = _create_pref(client)

    body = _parse(client, "Mua giày Nike 2tr")

    assert body["model"] == "classification_preference"
    assert body["warnings"] == []
    [draft] = body["drafts"]
    assert draft["amount"] == 2_000_000
    assert draft["direction"] == "expense"
    assert draft["occurred_on"] == TODAY
    assert draft["note"] == "Mua giày Nike"
    assert draft["category_slug"] == "shopping"
    assert draft["category_id"] == categories["shopping"]["id"]
    assert draft["spending_type"] == "essential"
    assert draft["matched_preference_id"] == pref["id"]
    assert draft["confidence"] >= 0.95
    assert "giay" in draft["reason"]


def test_shortcut_strips_leading_time_word(client, no_ai):
    _create_pref(client)

    [draft] = _parse(client, "hôm nay mua giày Nike 2tr")["drafts"]

    assert draft["note"] == "Mua giày Nike"


@pytest.mark.parametrize(
    "text",
    [
        "Hôm qua mua giày Nike 2tr",  # ngày tương đối
        "Mua giày 2tr ngày 5/10",  # còn chữ số ngoài số tiền
        "Mua giày Nike 2tr, áo 500k",  # nhiều khoản tiền
        "Bán giày cũ 1tr",  # chiều tiền có thể ngược (thu nhập)
        "t7 mua giày 2tr",
    ],
)
def test_shortcut_skipped_when_text_needs_model(client, fake_ai, text):
    calls, responses = fake_ai
    _create_pref(client)
    responses.append(_output(_draft(amount=2_000_000, note="Mua giày")))

    _parse(client, text)

    assert len(calls) == 1


def test_broad_preference_never_shortcuts(client, db, categories, fake_ai):
    """Test case #8: pattern quá rộng (`mua`) không được áp dụng thẳng."""
    calls, responses = fake_ai
    db.add(
        ClassificationPreference(
            pattern="mua",
            example_text="mua",
            category_id=categories["shopping"]["id"],
            spending_type="essential",
        )
    )
    db.flush()
    responses.append(_output(_draft(note="Mua đồ", category_slug="other", amount=50_000)))

    [draft] = _parse(client, "Mua đồ 50k")["drafts"]

    assert len(calls) == 1
    assert draft["category_slug"] == "other"
    assert draft["matched_preference_id"] is None


def test_preference_of_archived_category_ignored(client, categories, fake_ai):
    calls, responses = fake_ai
    _create_pref(client)
    client.patch(f"/api/v1/categories/{categories['shopping']['id']}", json={"is_archived": True})
    responses.append(_output(_draft(category_slug="other", amount=2_000_000)))

    [draft] = _parse(client, "Mua giày Nike 2tr")["drafts"]

    assert len(calls) == 1
    assert draft["matched_preference_id"] is None


# ---------- LLM path: few-shot + hậu kiểm theo preference ----------


def test_few_shot_contains_only_related_preferences(client, fake_ai):
    calls, responses = fake_ai
    _create_pref(
        client, pattern="sửa laptop", category_slug="electronics", spending_type="irregular"
    )
    _create_pref(client, pattern="giày")
    responses.append(_output(_draft(note="Sửa xe", category_slug="transport", amount=500_000)))

    _parse(client, "hôm qua sửa xe 500k")

    system_prompt = calls[0]["messages"][0]["content"]
    assert "“sua laptop”" in system_prompt
    assert "`irregular`" in system_prompt
    assert "“giay”" not in system_prompt


def test_prompt_without_preferences(client, fake_ai):
    calls, responses = fake_ai
    responses.append(_output(_draft(note="Mua áo", amount=450_000)))

    _parse(client, "Mua áo 450k")

    assert "(chưa có sở thích nào liên quan)" in calls[0]["messages"][0]["content"]


def test_model_draft_overridden_per_transaction(client, categories, fake_ai):
    """Câu nhiều khoản: chỉ khoản khớp preference bị phân loại lại."""
    calls, responses = fake_ai
    pref = _create_pref(client)
    responses.append(
        _output(
            _draft(note="Cafe", category_slug="food", amount=35_000),
            _draft(note="Mua giày", amount=2_000_000),
        )
    )

    body = _parse(client, "sáng cafe 35k, mua giày 2tr")

    cafe, shoes = body["drafts"]
    assert body["model"] == openai_client.model_fast()
    assert cafe["matched_preference_id"] is None
    assert cafe["spending_type"] == "non_essential"
    assert shoes["matched_preference_id"] == pref["id"]
    assert shoes["spending_type"] == "essential"
    assert shoes["category_id"] == categories["shopping"]["id"]
    assert shoes["confidence"] >= 0.95


def test_model_draft_override_respects_direction(client, fake_ai):
    _, responses = fake_ai
    _create_pref(client)
    income = _draft(
        direction="income",
        note="Bán giày cũ",
        category_slug="other_income",
        spending_type=None,
        amount=1_000_000,
    )
    responses.append(_output(income))

    [draft] = _parse(client, "Bán giày cũ 1tr")["drafts"]

    assert draft["category_slug"] == "other_income"
    assert draft["matched_preference_id"] is None


# ---------- học từ correction ----------


def test_correction_records_feedback_and_learns(client, db, categories, fake_ai):
    """Test case #4: AI shopping/non_essential → user sửa essential → feedback + preference."""
    _, responses = fake_ai
    responses.append(_output(_draft()))
    parsed = _parse(client, "Mua giày MLB 1.8 triệu")

    tx = _save(client, parsed, spending_type="essential")

    learned = tx["learned_preference"]
    assert learned["pattern"] == "giay"
    assert learned["spending_type"] == "essential"
    assert learned["category"]["slug"] == "shopping"
    assert learned["hit_count"] >= 1
    assert learned["example_text"] == "Mua giày MLB 1.8 triệu"

    [feedback] = db.scalars(
        select(ClassificationFeedback).where(ClassificationFeedback.transaction_id == tx["id"])
    ).all()
    assert str(feedback.ai_category_id) == categories["shopping"]["id"]
    assert feedback.ai_spending_type == "non_essential"
    assert str(feedback.final_category_id) == categories["shopping"]["id"]
    assert feedback.final_spending_type == "essential"

    assert [p["pattern"] for p in _prefs(client)] == ["giay"]


def test_learned_preference_used_next_time(client, fake_ai):
    """Correction → lần sau "Mua giày Nike 2tr" đi shortcut, không gọi OpenAI."""
    calls, responses = fake_ai
    responses.append(_output(_draft()))
    learned = _save(client, _parse(client, "Mua giày MLB 1.8 triệu"), spending_type="essential")[
        "learned_preference"
    ]

    [draft] = _parse(client, "Mua giày Nike 2tr")["drafts"]

    assert len(calls) == 1
    assert draft["matched_preference_id"] == learned["id"]
    assert draft["spending_type"] == "essential"


def test_income_unchanged_no_feedback(client, db, fake_ai):
    """Test case #5: income salary/null giữ nguyên → không feedback, không preference."""
    _, responses = fake_ai
    responses.append(
        _output(
            _draft(
                direction="income",
                amount=25_000_000,
                note="Nhận lương",
                category_slug="salary",
                spending_type=None,
            )
        )
    )

    tx = _save(client, _parse(client, "Nhận lương 25 triệu"))

    assert tx["learned_preference"] is None
    assert db.scalars(select(ClassificationFeedback)).all() == []
    assert _prefs(client) == []


def test_income_category_correction_learns_null_spending_type(client, categories, fake_ai):
    _, responses = fake_ai
    responses.append(
        _output(
            _draft(
                direction="income",
                amount=5_000_000,
                note="Tiền Upwork",
                category_slug="other_income",
                spending_type=None,
            )
        )
    )

    tx = _save(
        client,
        _parse(client, "Nhận tiền Upwork 5tr"),
        category_id=categories["freelance"]["id"],
    )

    learned = tx["learned_preference"]
    assert learned["pattern"] == "tien upwork"
    assert learned["category"]["slug"] == "freelance"
    assert learned["spending_type"] is None


def test_manual_transaction_without_ai_suggestion_not_learned(client, db, categories):
    resp = client.post(
        TX_URL,
        json={
            "direction": "expense",
            "amount": 2_000_000,
            "occurred_on": TODAY,
            "category_id": categories["shopping"]["id"],
            "spending_type": "essential",
            "note": "Mua giày",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["learned_preference"] is None
    assert db.scalars(select(ClassificationFeedback)).all() == []


def test_correction_on_multi_transaction_uses_draft_note(client, fake_ai):
    _, responses = fake_ai
    responses.append(
        _output(
            _draft(note="Cafe", category_slug="food", amount=35_000),
            _draft(note="Mua giày", amount=2_000_000),
        )
    )
    parsed = _parse(client, "sáng cafe 35k, mua giày 2tr")

    tx = _save(client, parsed, index=1, spending_type="essential")

    assert tx["learned_preference"]["pattern"] == "giay"


def test_correction_without_keyword_records_feedback_only(client, db, fake_ai):
    _, responses = fake_ai
    responses.append(_output(_draft(note="Mua", amount=50_000)))
    parsed = _parse(client, "mua 50k")

    tx = _save(client, parsed, spending_type="essential")

    assert tx["learned_preference"] is None
    assert len(db.scalars(select(ClassificationFeedback)).all()) == 1
    assert _prefs(client) == []


def test_confirm_preference_draft_increments_hit_count(client, no_ai):
    pref = _create_pref(client)
    assert pref["hit_count"] == 0

    tx = _save(client, _parse(client, "Mua giày Nike 2tr"))

    assert tx["learned_preference"] is None
    [stored] = _prefs(client)
    assert stored["hit_count"] == 1
    assert stored["last_used_at"] is not None


def test_correcting_preference_draft_updates_that_preference(client, categories, no_ai):
    pref = _create_pref(
        client, pattern="sửa laptop", category_slug="electronics", spending_type="irregular"
    )
    parsed = _parse(client, "Sửa màn hình laptop 900k")
    assert parsed["drafts"][0]["matched_preference_id"] == pref["id"]

    tx = _save(client, parsed, spending_type="non_essential")

    learned = tx["learned_preference"]
    assert learned["id"] == pref["id"]
    assert learned["pattern"] == "sua laptop"
    assert learned["spending_type"] == "non_essential"
    assert learned["hit_count"] == 1
    assert len(_prefs(client)) == 1


def test_confirmations_accumulate_hit_count(client, fake_ai):
    """Correction lần 1 tạo preference; lần sau model đi đường LLM (có ngày) nhưng draft được
    phân loại theo preference, user giữ nguyên → hit_count tăng."""
    _, responses = fake_ai
    responses.append(_output(_draft()))
    _save(client, _parse(client, "Mua giày MLB 1.8 triệu hôm qua"), spending_type="essential")

    responses.append(_output(_draft(note="Mua giày Vans", amount=1_000_000)))
    parsed = _parse(client, "Mua giày Vans 1tr hôm qua")
    assert parsed["drafts"][0]["spending_type"] == "essential"
    tx = _save(client, parsed)

    assert tx["learned_preference"] is None
    [stored] = _prefs(client)
    assert stored["hit_count"] == 2
    assert stored["example_text"] == "Mua giày MLB 1.8 triệu hôm qua"


# ---------- CRUD ----------


def test_delete_preference_then_not_used(client, fake_ai):
    """Test case #6."""
    calls, responses = fake_ai
    pref = _create_pref(client)

    resp = client.delete(f"{PREF_URL}/{pref['id']}")
    assert resp.status_code == 204
    assert _prefs(client) == []

    responses.append(_output(_draft(amount=2_000_000, note="Mua giày Nike")))
    [draft] = _parse(client, "Mua giày Nike 2tr")["drafts"]

    assert len(calls) == 1
    assert draft["matched_preference_id"] is None
    assert draft["spending_type"] == "non_essential"
    assert "“giay”" not in calls[0]["messages"][0]["content"]


def test_delete_unknown_preference_404(client):
    resp = client.delete(f"{PREF_URL}/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404
    assert resp.json()["code"] == "preference_not_found"


def test_create_preference_normalizes_and_upserts(client, categories):
    first = _create_pref(client, pattern="  Giày ")
    second = _create_pref(client, pattern="giay", spending_type="non_essential")

    assert first["pattern"] == "giay"
    assert second["id"] == first["id"]
    assert second["spending_type"] == "non_essential"
    assert len(_prefs(client)) == 1


def test_create_preference_defaults_spending_type(client):
    resp = client.post(PREF_URL, json={"pattern": "sách", "category_slug": "education"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["spending_type"] == "essential"
    assert body["example_text"] == "sách"
    assert body["hit_count"] == 0
    assert body["last_used_at"] is None


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"pattern": "mua", "category_slug": "shopping"}, "preference_too_broad"),
        ({"pattern": "giày", "category_slug": "khong_co"}, "category_not_found"),
        (
            {"pattern": "lương", "category_slug": "salary", "spending_type": "essential"},
            "income_spending_type",
        ),
        ({"pattern": "giày", "category_slug": "shopping", "extra": 1}, "validation_error"),
        ({"pattern": "", "category_slug": "shopping"}, "validation_error"),
    ],
)
def test_create_preference_invalid(client, payload, code):
    resp = client.post(PREF_URL, json=payload)

    assert resp.status_code == 422
    assert resp.json()["code"] == code


def test_create_preference_archived_category(client, categories):
    client.patch(f"/api/v1/categories/{categories['gifts']['id']}", json={"is_archived": True})

    resp = client.post(PREF_URL, json={"pattern": "quà cưới", "category_slug": "gifts"})

    assert resp.status_code == 422
    assert resp.json()["code"] == "category_archived"


def test_list_preferences_filters(client, categories):
    _create_pref(client, pattern="giày")
    _create_pref(client, pattern="cafe", category_slug="food", spending_type="non_essential")

    assert {p["pattern"] for p in _prefs(client)} == {"giay", "cafe"}
    by_category = client.get(PREF_URL, params={"category_id": categories["food"]["id"]}).json()
    assert [p["pattern"] for p in by_category["items"]] == ["cafe"]
    by_q = client.get(PREF_URL, params={"q": "Giày"}).json()
    assert [p["pattern"] for p in by_q["items"]] == ["giay"]
    limited = client.get(PREF_URL, params={"limit": 1}).json()
    assert len(limited["items"]) == 1


# ---------- explicit preference ----------


def _pref_output(**overrides) -> str:
    return json.dumps(
        {
            "pattern": "giày",
            "category_slug": "shopping",
            "spending_type": "essential",
            "confidence": 0.9,
            "reason": "Bạn coi giày là nhu cầu thiết yếu",
            **overrides,
        }
    )


def test_parse_explicit_preference(client, categories, fake_ai):
    """Test case #7: "Tao coi giày là thiết yếu" → draft, không lưu."""
    calls, responses = fake_ai
    responses.append(_pref_output())

    resp = client.post(f"{PREF_URL}/parse", json={"text": "Tao coi giày là thiết yếu"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pattern"] == "giay"
    assert body["category_slug"] == "shopping"
    assert body["category_id"] == categories["shopping"]["id"]
    assert body["spending_type"] == "essential"
    assert body["example_text"] == "Tao coi giày là thiết yếu"
    assert body["warnings"] == []
    assert calls[0]["messages"][1]["content"] == "Tao coi giày là thiết yếu"
    assert "| shopping | Mua sắm | expense | non_essential |" in calls[0]["messages"][0]["content"]
    assert _prefs(client) == []


def test_parse_explicit_preference_then_confirm(client, fake_ai):
    _, responses = fake_ai
    responses.append(
        _pref_output(pattern="sửa laptop", category_slug="electronics", spending_type="irregular")
    )
    draft = client.post(f"{PREF_URL}/parse", json={"text": "Sửa laptop là bất thường"}).json()

    resp = client.post(
        PREF_URL,
        json={
            "pattern": draft["pattern"],
            "category_slug": draft["category_slug"],
            "spending_type": draft["spending_type"],
            "example_text": draft["example_text"],
        },
    )

    assert resp.status_code == 201
    [draft_after] = _parse(client, "sửa màn hình laptop 900k")["drafts"]
    assert draft_after["spending_type"] == "irregular"
    assert draft_after["matched_preference_id"] == resp.json()["id"]


def test_parse_explicit_preference_warns_on_replace_and_low_confidence(client, fake_ai):
    _, responses = fake_ai
    _create_pref(client, spending_type="non_essential")
    responses.append(_pref_output(confidence=0.3))

    body = client.post(f"{PREF_URL}/parse", json={"text": "giày thiết yếu"}).json()

    assert len(body["warnings"]) == 2
    assert "thay" in body["warnings"][1]


def test_parse_explicit_income_defaults_null(client, fake_ai):
    _, responses = fake_ai
    responses.append(_pref_output(pattern="Upwork", category_slug="freelance", spending_type=None))

    body = client.post(f"{PREF_URL}/parse", json={"text": "Tiền Upwork là freelance"}).json()

    assert body["pattern"] == "upwork"
    assert body["spending_type"] is None


def test_parse_explicit_expense_without_type_uses_category_default(client, fake_ai):
    _, responses = fake_ai
    responses.append(_pref_output(spending_type=None))

    body = client.post(f"{PREF_URL}/parse", json={"text": "giày là mua sắm"}).json()

    assert body["spending_type"] == "non_essential"


@pytest.mark.parametrize(
    "bad",
    [
        {"category_slug": "khong_co"},
        {"pattern": "mua"},
        {"category_slug": "salary", "spending_type": "essential"},
    ],
)
def test_parse_explicit_invalid_output_retried_then_502(client, fake_ai, bad):
    calls, responses = fake_ai
    responses += [_pref_output(**bad)] * 2

    resp = client.post(f"{PREF_URL}/parse", json={"text": "Tao coi giày là thiết yếu"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_INVALID_OUTPUT"
    assert len(calls) == 2


def test_parse_explicit_not_configured(client, no_ai):
    resp = client.post(f"{PREF_URL}/parse", json={"text": "Tao coi giày là thiết yếu"})

    assert resp.status_code == 503
    assert resp.json()["code"] == "AI_NOT_CONFIGURED"
