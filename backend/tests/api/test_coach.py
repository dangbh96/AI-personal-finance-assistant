"""API Financial Coach (phase-10 § 6) — model giả qua `openai_client._chat_tools`, DB test thật."""

import json
from decimal import Decimal

import httpx
import openai
import pytest

from app.ai import openai_client
from app.ai.openai_client import ToolCallData, ToolChatResult
from app.models import BudgetAllocation
from app.services import coach_guard
from tests import coach_dataset
from tests.coach_dataset import OCTOBER, SEPTEMBER, TODAY

FAKE_MODEL = "gpt-4o-2024-08-06"
TOOLS = {
    "get_spending_summary",
    "get_budget_status",
    "get_category_trend",
    "get_budget_advice",
    "get_recent_reviews",
}

GOOD_ANSWER = (
    "**Quan sát**\n"
    "- Ăn uống tháng 09/2026: 4.200.000 ₫ (cao nhất).\n"
    "- Mua sắm tháng 09/2026: 3.800.000 ₫, vượt ngân sách 1.800.000 ₫.\n\n"
    "**Vì sao**\n"
    "Mua sắm biến động lớn nhất trong 3 tháng, một phần do khoản Nồi chiên 2.000.000 ₫.\n\n"
    "**Bạn có thể cân nhắc**\n"
    "Nếu bạn muốn, bạn có thể đặt giới hạn cho mua sắm ở [Ngân sách](/budget)."
)


def call(name: str, args: dict, call_id: str) -> ToolCallData:
    return ToolCallData(id=call_id, name=name, arguments=json.dumps(args))


def result(content: str | None = None, calls: list[ToolCallData] | None = None) -> ToolChatResult:
    return ToolChatResult(
        content=content,
        tool_calls=calls or [],
        finish_reason="tool_calls" if calls else "stop",
        prompt_tokens=1000,
        completion_tokens=200,
        model=FAKE_MODEL,
    )


@pytest.fixture
def fake_llm(monkeypatch):
    """Model giả: trả lần lượt `responses` (ToolChatResult hoặc exception), ghi lại kwargs."""
    calls: list[dict] = []
    responses: list = []

    def _fake(**kwargs):
        calls.append(kwargs)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_chat_tools", _fake)
    return calls, responses


@pytest.fixture
def seeded(db):
    return coach_dataset.seed_all(db)


def _session(client, title: str | None = None) -> dict:
    body = {} if title is None else {"title": title}
    resp = client.post("/api/v1/coach/sessions", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ask(client, session_id: str, content: str, today: str = TODAY.isoformat()):
    return client.post(
        f"/api/v1/coach/sessions/{session_id}/messages",
        json={"content": content, "today": today},
    )


# ---------- sessions ----------


def test_session_crud(client):
    created = _session(client)
    assert created["title"] == "Cuộc trò chuyện mới"
    other = _session(client, "  Ngân sách tháng 10  ")
    assert other["title"] == "Ngân sách tháng 10"

    items = client.get("/api/v1/coach/sessions").json()["items"]
    assert {s["id"] for s in items} >= {created["id"], other["id"]}
    assert all(s["message_count"] == 0 and s["last_message_preview"] is None for s in items)

    resp = client.patch(f"/api/v1/coach/sessions/{created['id']}", json={"title": "Đổi tên"})
    assert resp.status_code == 200 and resp.json()["title"] == "Đổi tên"
    detail = client.get(f"/api/v1/coach/sessions/{created['id']}").json()
    assert detail["title"] == "Đổi tên" and detail["messages"] == []

    assert client.delete(f"/api/v1/coach/sessions/{created['id']}").status_code == 204
    resp = client.get(f"/api/v1/coach/sessions/{created['id']}")
    assert resp.status_code == 404 and resp.json()["code"] == "chat_session_not_found"
    assert client.delete(f"/api/v1/coach/sessions/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "body", [{"title": ""}, {"title": "x" * 121}, {"title": "ok", "user_id": "x"}]
)
def test_session_validation(client, body):
    resp = client.post("/api/v1/coach/sessions", json=body)
    assert resp.status_code == 422 and resp.json()["code"] == "validation_error"


def test_message_validation(client, fake_llm):
    session = _session(client)
    assert _ask(client, session["id"], "   ").status_code == 422
    assert _ask(client, session["id"], "x" * 2001).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    resp = _ask(client, missing, "Tháng này khoản nào vượt budget?")
    assert resp.status_code == 404 and resp.json()["code"] == "chat_session_not_found"
    assert fake_llm[0] == []


# ---------- hội thoại (test case 3, 7 bằng model giả) ----------


def test_post_message_runs_tools_and_persists(client, seeded, fake_llm):
    calls, responses = fake_llm
    responses += [
        result(
            calls=[
                call("get_category_trend", {"months": 3}, "c1"),
                call("get_budget_status", {"month": "2026-09-01"}, "c2"),
            ]
        ),
        result(GOOD_ANSWER),
    ]
    session = _session(client)
    resp = _ask(client, session["id"], "Tao nên giảm khoản nào?")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["guard_status"] == "passed"
    assert data["session"]["title"] == "Nên giảm khoản nào"
    assert data["user_message"]["role"] == "user"
    assistant = data["assistant_message"]
    assert assistant["role"] == "assistant" and assistant["content"] == GOOD_ANSWER

    trace = data["tool_trace"]
    assert [t["name"] for t in trace] == ["get_category_trend", "get_budget_status"]
    assert trace[0]["args"] == {"months": 3}
    assert trace[0]["result_summary"] == "3 danh mục · 3 tháng (07/2026–09/2026)"
    assert trace[0]["result_count"] == 3
    assert trace[1]["result_summary"] == "3 dòng ngân sách · tháng 09/2026"
    assert all(t["latency_ms"] >= 0 and t["error"] is None for t in trace)

    evidence = data["evidence"]
    rows = {(e["label"], e["period"], e["metric"], e["amount"]) for e in evidence}
    assert ("Ăn uống", "09/2026", "Chi tiêu", 4_200_000) in rows
    assert ("Mua sắm", "09/2026", "Chi tiêu", 3_800_000) in rows
    assert ("Mua sắm", "09/2026", "Chênh lệch", 1_800_000) in rows
    assert [e["ref"] for e in evidence] == [f"E{i + 1}" for i in range(len(evidence))]
    refs = {r for t in trace for r in t["evidence_refs"]}
    assert refs == {e["ref"] for e in evidence}
    assert all(e["amount"] in {4_200_000, 3_800_000, 1_800_000, 2_000_000} for e in evidence)

    meta = assistant["metadata"]
    assert meta["model"] == FAKE_MODEL and meta["prompt_version"] == "coach_v1"
    assert (meta["input_tokens"], meta["output_tokens"], meta["total_tokens"]) == (
        2000,
        400,
        2400,
    )
    assert meta["llm_calls"] == 2 and meta["tool_rounds"] == 1
    # gpt-4o: (2000 × 2,5 + 400 × 10) / 1e6 USD × 26.000 = 234 đồng
    assert meta["estimated_cost_vnd"] == 234
    assert meta["guard_status"] == "passed" and meta["guard_problems"] == []

    # Lời gọi model: 5 tool read-only (tool tương lai chưa đăng ký bị bỏ qua), có system prompt.
    first = calls[0]
    assert {t["function"]["name"] for t in first["tools"]} == TOOLS
    assert first["tool_choice"] == "auto"
    assert first["messages"][0]["role"] == "system"
    assert "2026-10-05" in first["messages"][0]["content"]
    assert first["messages"][-1] == {"role": "user", "content": "Tao nên giảm khoản nào?"}
    second = calls[1]["messages"]
    tool_messages = [m for m in second if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["c1", "c2"]
    trend = json.loads(tool_messages[0]["content"])
    assert {i["category_slug"]: i["latest_total"] for i in trend["items"]}["food"] == 4_200_000

    # Refresh: lịch sử + tool trace + evidence vẫn còn.
    detail = client.get(f"/api/v1/coach/sessions/{session['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    stored = detail["messages"][1]
    assert stored["tool_calls"] == trace and stored["evidence"] == evidence
    listed = client.get("/api/v1/coach/sessions").json()["items"][0]
    assert listed["id"] == session["id"] and listed["message_count"] == 2
    assert listed["last_message_preview"].startswith("Quan sát")


def test_coach_does_not_modify_budget(client, db, seeded, fake_llm):
    _, responses = fake_llm
    responses += [
        result(calls=[call("get_budget_status", {"month": "2026-09-01"}, "c1")]),
        result(GOOD_ANSWER),
    ]
    before = {a.id: a.planned_amount for b in seeded.values() for a in b.allocations}
    session = _session(client)
    assert _ask(client, session["id"], "Tháng 9 khoản nào vượt budget?").status_code == 200
    db.expire_all()
    after = {a.id: a.planned_amount for a in db.query(BudgetAllocation).all() if a.id in before}
    assert after == before


def test_history_is_sent_with_next_question(client, seeded, fake_llm):
    calls, responses = fake_llm
    session = _session(client)
    responses += [result("Chào bạn, mình có thể giúp gì về chi tiêu?")]
    assert _ask(client, session["id"], "Chào coach").json()["guard_status"] == "passed"
    responses += [result("Bạn có thể hỏi về ngân sách tháng này.")]
    assert _ask(client, session["id"], "Mình hỏi gì được?").status_code == 200
    roles = [(m["role"], m.get("content")) for m in calls[1]["messages"][1:]]
    assert roles == [
        ("user", "Chào coach"),
        ("assistant", "Chào bạn, mình có thể giúp gì về chi tiêu?"),
        ("user", "Mình hỏi gì được?"),
    ]


def test_out_of_scope_refusal_without_ai(client, fake_llm):
    session = _session(client)
    resp = _ask(client, session["id"], "Mua cổ phiếu nào tuần này?")
    assert resp.status_code == 200
    data = resp.json()
    assert data["guard_status"] == "refused_out_of_scope"
    content = data["assistant_message"]["content"]
    assert "không tư vấn đầu tư" in content
    assert data["tool_trace"] == [] and data["evidence"] == []
    meta = data["assistant_message"]["metadata"]
    assert meta["model"] is None and meta["total_tokens"] == 0 and meta["llm_calls"] == 0
    assert fake_llm[0] == []


def test_write_request_refused_with_links(client, db, seeded, fake_llm):
    session = _session(client)
    resp = _ask(client, session["id"], "Tự giảm budget mua sắm giúp tao")
    data = resp.json()
    assert data["guard_status"] == "refused_write_request"
    content = data["assistant_message"]["content"]
    assert "(/budget)" in content and "(/budget/advice)" in content
    assert "không tự thay đổi" in content
    assert fake_llm[0] == []
    preview = client.get("/api/v1/coach/sessions").json()["items"][0]["last_message_preview"]
    assert preview.startswith("Coach chỉ đọc dữ liệu") and "](/" not in preview
    shopping = [
        a for a in seeded[SEPTEMBER].allocations if a.category and a.category.slug == "shopping"
    ][0]
    db.refresh(shopping)
    assert shopping.planned_amount == 2_000_000


# ---------- response_guard (test case 5, 6 qua graph) ----------


def test_guard_rewrites_once(client, seeded, fake_llm):
    calls, responses = fake_llm
    bad = GOOD_ANSWER.replace("cao nhất", "bạn tiêu quá nhiều").replace("2.000.000", "9.999.999")
    responses += [
        result(calls=[call("get_category_trend", {"months": 3}, "c1")]),
        result(bad),
        result(GOOD_ANSWER.replace(", vượt ngân sách 1.800.000 ₫", "")),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Tao nên giảm khoản nào?").json()
    assert data["guard_status"] == "rewritten"
    problems = data["assistant_message"]["metadata"]["guard_problems"]
    assert any("bạn tiêu quá nhiều" in p for p in problems)
    assert any("9.999.999" in p for p in problems)
    feedback = calls[2]["messages"][-1]
    assert feedback["role"] == "user" and "chưa đạt kiểm tra" in feedback["content"]
    assert "bạn tiêu quá nhiều" not in data["assistant_message"]["content"]


def test_guard_falls_back_after_second_failure(client, seeded, fake_llm):
    _, responses = fake_llm
    bad = "**Quan sát**\nBạn tiêu quá nhiều: 9.999.999 ₫.\n**Vì sao**\nLãng phí.\nBạn phải cắt."
    responses += [
        result(calls=[call("get_category_trend", {"months": 3}, "c1")]),
        result(bad),
        result(bad),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Tao nên giảm khoản nào?").json()
    assert data["guard_status"] == "fallback"
    content = data["assistant_message"]["content"]
    assert "9.999.999" not in content and "Quan sát" in content
    assert "4.000.000 ₫" in content
    assert data["evidence"] and data["tool_trace"][0]["evidence_refs"]
    allowed = coach_guard.allowed_numbers([], "", TODAY) | {
        Decimal(e["amount"]) for e in data["evidence"]
    }
    assert coach_guard.check_answer(content, allowed) == []


def test_tool_rounds_are_capped_at_six(client, seeded, fake_llm):
    calls, responses = fake_llm
    responses += [result(calls=[call("get_budget_status", {}, f"c{i}")]) for i in range(6)] + [
        result("Bạn có thể xem chi tiết ở [Ngân sách](/budget).")
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Tháng này thế nào?").json()
    assert len(calls) == 7
    assert [c["tool_choice"] for c in calls] == ["auto"] * 6 + ["none"]
    assert len(data["tool_trace"]) == 6
    assert data["assistant_message"]["metadata"]["tool_rounds"] == 6
    assert data["guard_status"] == "passed"


def test_tool_error_is_returned_to_model(client, seeded, fake_llm):
    calls, responses = fake_llm
    responses += [
        result(calls=[call("get_category_trend", {"category_slug": "khong_co"}, "c1")]),
        result("Mình chưa tìm thấy danh mục đó, bạn có thể hỏi về Ăn uống hoặc Mua sắm."),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Danh mục khong_co tăng không?").json()
    trace = data["tool_trace"][0]
    assert trace["error"] and "khong_co" in trace["error"] and trace["result_count"] == 0
    tool_message = [m for m in calls[1]["messages"] if m["role"] == "tool"][0]
    assert "khong_co" in tool_message["content"]


# ---------- lỗi AI (test case 8) ----------

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (openai.APITimeoutError(request=_REQUEST), "AI_TIMEOUT"),
        (openai.APIConnectionError(request=_REQUEST), "AI_UNAVAILABLE"),
    ],
)
def test_ai_failure_returns_503_and_keeps_user_message(client, seeded, fake_llm, error, code):
    _, responses = fake_llm
    responses.append(error)
    session = _session(client)
    resp = _ask(client, session["id"], "Tháng này khoản nào vượt budget?")
    assert resp.status_code == 503 and resp.json()["code"] == code
    detail = client.get(f"/api/v1/coach/sessions/{session['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user"]
    assert detail["title"] == "Tháng này khoản nào vượt budget"


def test_ai_not_configured_returns_503(client, monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    session = _session(client)
    resp = _ask(client, session["id"], "Tháng này khoản nào vượt budget?")
    assert resp.status_code == 503 and resp.json()["code"] == "AI_NOT_CONFIGURED"
    # Câu hỏi ngoài phạm vi vẫn trả lời được (không cần AI).
    resp = _ask(client, session["id"], "Có nên mua bitcoin không?")
    assert resp.status_code == 200
    assert resp.json()["guard_status"] == "refused_out_of_scope"


def test_october_budget_status_is_current_month(client, seeded, fake_llm):
    calls, responses = fake_llm
    responses += [
        result(calls=[call("get_budget_status", {}, "c1")]),
        result(
            "**Quan sát**\n- Mua sắm tháng 10/2026: đã chi 500.000 ₫ trên ngân sách "
            "2.000.000 ₫.\n**Vì sao**\nMới qua 5 ngày đầu tháng.\n**Bạn có thể cân nhắc**\n"
            "Nếu bạn muốn, có thể theo dõi tiếp ở [Ngân sách](/budget)."
        ),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Tháng này mua sắm thế nào?").json()
    assert data["guard_status"] == "passed", data["assistant_message"]["metadata"]
    assert data["tool_trace"][0]["result_summary"] == "3 dòng ngân sách · tháng 10/2026"
    rows = {(e["label"], e["metric"], e["amount"]) for e in data["evidence"]}
    assert ("Mua sắm", "Thực chi", 500_000) in rows
    assert ("Mua sắm", "Ngân sách", 2_000_000) in rows
    assert seeded[OCTOBER].period_month == OCTOBER
