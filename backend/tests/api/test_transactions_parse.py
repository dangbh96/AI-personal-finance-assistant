"""`POST /transactions/parse` với OpenAI giả (không cần API key) + lưu draft đã xác nhận."""

import json
from datetime import date

import pytest

from app.ai import nl_transaction_parser, openai_client

URL = "/api/v1/transactions"
PARSE_URL = f"{URL}/parse"


def _draft(**overrides) -> dict:
    return {
        "direction": "expense",
        "amount": 55_000,
        "occurred_on": "2026-10-07",
        "note": "Ăn phở",
        "category_slug": "food",
        "spending_type": "essential",
        "confidence": 0.92,
        "reason": "Bữa ăn chính hằng ngày",
        **overrides,
    }


def _output(*drafts: dict, warnings: list[str] | None = None) -> str:
    return json.dumps({"transactions": list(drafts), "warnings": warnings or []})


def test_parse_single_transaction(client, categories, fake_ai):
    """Test case #1."""
    calls, responses = fake_ai
    responses.append(_output(_draft()))

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["raw_input"] == "Hôm nay ăn phở 55k"
    assert body["model"] == openai_client.model_fast()
    assert body["warnings"] == []
    [draft] = body["drafts"]
    assert draft["amount"] == 55_000
    assert draft["direction"] == "expense"
    assert draft["occurred_on"] == "2026-10-07"
    assert draft["category_slug"] == "food"
    assert draft["category_id"] == categories["food"]["id"]
    assert draft["spending_type"] == "essential"

    system_prompt = calls[0]["messages"][0]["content"]
    assert "2026-10-07" in system_prompt
    assert "| food | Ăn uống | expense | essential |" in system_prompt
    assert "55000" in system_prompt  # gợi ý số tiền deterministic
    assert calls[0]["messages"][1] == {"role": "user", "content": "Hôm nay ăn phở 55k"}


def test_parse_does_not_write_db(client, fake_ai):
    _, responses = fake_ai
    responses.append(_output(_draft()))
    before = client.get(URL).json()["total"]

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 200
    assert client.get(URL).json()["total"] == before


def test_parse_multiple_transactions_not_summed(client, fake_ai):
    """Test case #5."""
    _, responses = fake_ai
    responses.append(
        _output(
            _draft(amount=35_000, note="Cafe", spending_type="non_essential"),
            _draft(amount=60_000, note="Cơm trưa"),
        )
    )

    resp = client.post(
        PARSE_URL, json={"text": "sáng cafe 35k, trưa cơm 60k", "today": "2026-10-07"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert [d["amount"] for d in body["drafts"]] == [35_000, 60_000]
    assert body["warnings"] == []


def test_parse_unknown_category_from_ai_retried_then_502(client, fake_ai):
    """Test case #2: AI bịa category ngoài danh sách → sửa 1 lần, vẫn sai → 502."""
    calls, responses = fake_ai
    responses += [_output(_draft(category_slug="unknown"))] * 2

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_INVALID_OUTPUT"
    assert len(calls) == 2
    feedback = calls[1]["messages"][-1]["content"]
    assert "unknown" in feedback
    assert "food" in feedback


def test_parse_unknown_category_fixed_on_retry(client, fake_ai):
    calls, responses = fake_ai
    responses += [_output(_draft(category_slug="pho")), _output(_draft())]

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 200
    assert resp.json()["drafts"][0]["category_slug"] == "food"
    assert len(calls) == 2


def test_parse_category_kind_mismatch_rejected(client, fake_ai):
    _, responses = fake_ai
    responses += [_output(_draft(category_slug="salary"))] * 2

    resp = client.post(PARSE_URL, json={"text": "ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_INVALID_OUTPUT"


def test_parse_archived_category_not_offered(client, categories, fake_ai):
    calls, responses = fake_ai
    client.patch(f"/api/v1/categories/{categories['gifts']['id']}", json={"is_archived": True})
    responses += [_output(_draft(category_slug="gifts"))] * 2

    resp = client.post(PARSE_URL, json={"text": "mừng cưới 500k", "today": "2026-10-07"})

    assert resp.status_code == 502
    assert "| gifts |" not in calls[0]["messages"][0]["content"]


def test_parse_income_with_spending_type_retried_then_error(client, fake_ai):
    """Test case #6."""
    calls, responses = fake_ai
    bad = _draft(
        direction="income", amount=25_000_000, category_slug="salary", spending_type="essential"
    )
    responses += [_output(bad)] * 2

    resp = client.post(PARSE_URL, json={"text": "Nhận lương 25 triệu", "today": "2026-10-07"})

    assert resp.status_code == 502
    assert resp.json()["code"] == "AI_INVALID_OUTPUT"
    assert len(calls) == 2
    assert "income" in calls[1]["messages"][-1]["content"]


def test_parse_income_with_spending_type_fixed_on_retry(client, fake_ai):
    _, responses = fake_ai
    income = {"direction": "income", "amount": 25_000_000, "category_slug": "salary"}
    responses += [
        _output(_draft(**income, spending_type="essential")),
        _output(_draft(**income, spending_type=None, note="Nhận lương")),
    ]

    resp = client.post(PARSE_URL, json={"text": "Nhận lương 25 triệu", "today": "2026-10-07"})

    assert resp.status_code == 200
    [draft] = resp.json()["drafts"]
    assert draft["spending_type"] is None
    assert draft["direction"] == "income"


def test_parse_not_configured_returns_503(client, monkeypatch):
    """Test case #3."""
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)

    def _must_not_call(**_):
        raise AssertionError("không được gọi OpenAI khi chưa cấu hình")

    monkeypatch.setattr(openai_client, "_chat_json", _must_not_call)

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k"})

    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "AI_NOT_CONFIGURED"
    assert "thủ công" in body["detail"]


def test_parse_without_amount_rejected_before_calling_ai(client, fake_ai):
    calls, _ = fake_ai

    resp = client.post(PARSE_URL, json={"text": "ăn phở"})

    assert resp.status_code == 422
    assert resp.json()["code"] == "amount_missing"
    assert calls == []


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "phở 55k", "extra": 1}, {}])
def test_parse_invalid_request(client, fake_ai, payload):
    resp = client.post(PARSE_URL, json=payload)

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_parse_warns_when_amount_not_in_text(client, fake_ai):
    _, responses = fake_ai
    responses.append(_output(_draft(amount=550_000)))

    resp = client.post(PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"})

    assert resp.status_code == 200
    assert any("550.000 ₫" in w for w in resp.json()["warnings"])


def test_parse_warns_when_fewer_drafts_than_amounts(client, fake_ai):
    _, responses = fake_ai
    responses.append(_output(_draft(amount=35_000, note="Cafe")))

    resp = client.post(PARSE_URL, json={"text": "cafe 35k, phở 55k", "today": "2026-10-07"})

    assert any("2 khoản tiền" in w for w in resp.json()["warnings"])


def test_parse_warns_future_date_and_keeps_ai_warnings(client, fake_ai):
    _, responses = fake_ai
    responses.append(_output(_draft(occurred_on="2026-10-09"), warnings=["Ngày chưa rõ"]))

    resp = client.post(PARSE_URL, json={"text": "ăn phở 55k", "today": "2026-10-07"})

    warnings = resp.json()["warnings"]
    assert warnings[0] == "Ngày chưa rõ"
    assert any("tương lai" in w for w in warnings)


def test_parse_defaults_today_from_timezone(client, fake_ai, monkeypatch):
    calls, responses = fake_ai
    monkeypatch.setattr(nl_transaction_parser, "today_in", lambda tz: date(2026, 10, 7))
    responses.append(_output(_draft()))

    resp = client.post(PARSE_URL, json={"text": "ăn phở 55k"})

    assert resp.status_code == 200
    assert "Hôm nay là **2026-10-07 (thứ 4 (Thứ Tư))**" in calls[0]["messages"][0]["content"]


def test_save_confirmed_nl_draft(client, categories, fake_ai):
    """Test case #4: user xác nhận draft (đã sửa note) → lưu với source/raw_input/ai_suggestion."""
    _, responses = fake_ai
    responses.append(_output(_draft()))
    parsed = client.post(
        PARSE_URL, json={"text": "Hôm nay ăn phở 55k", "today": "2026-10-07"}
    ).json()
    draft = parsed["drafts"][0]

    resp = client.post(
        URL,
        json={
            "direction": draft["direction"],
            "amount": draft["amount"],
            "occurred_on": draft["occurred_on"],
            "category_id": draft["category_id"],
            "spending_type": draft["spending_type"],
            "note": "Phở bò",
            "source": "nl",
            "raw_input": parsed["raw_input"],
            "ai_suggestion": {**draft, "model": parsed["model"]},
        },
    )

    assert resp.status_code == 201, resp.text
    tx = resp.json()
    assert tx["source"] == "nl"
    assert tx["raw_input"] == "Hôm nay ăn phở 55k"
    assert tx["note"] == "Phở bò"
    assert tx["ai_suggestion"]["note"] == "Ăn phở"
    assert tx["ai_suggestion"]["category_slug"] == "food"
    assert tx["ai_suggestion"]["amount"] == 55_000

    fetched = client.get(f"{URL}/{tx['id']}").json()
    assert fetched["ai_suggestion"] == tx["ai_suggestion"]
    assert fetched["source"] == "nl"


def test_build_calendar_last_saturday():
    """Thứ 7 tuần trước khi hôm nay là Thứ Tư 2026-10-07 → 2026-10-03 (tuần từ Thứ Hai)."""
    calendar = nl_transaction_parser.build_calendar(date(2026, 10, 7))

    assert "thứ 2 (Thứ Hai) tuần trước: 2026-09-28" in calendar
    assert "thứ 7 (Thứ Bảy) tuần trước: 2026-10-03" in calendar
    assert "Chủ Nhật (CN) tuần trước: 2026-10-04" in calendar
    assert "thứ 4 (Thứ Tư) tuần này: 2026-10-07 ← hôm nay" in calendar
    assert "thứ 7 (Thứ Bảy) tuần này: 2026-10-10 (tương lai)" in calendar
    assert "Hôm qua: 2026-10-06" in calendar
    assert "Tháng trước: 2026-09-01 → 2026-09-30" in calendar
