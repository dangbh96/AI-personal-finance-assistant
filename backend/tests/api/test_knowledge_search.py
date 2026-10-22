"""Knowledge base / RAG (Phase 16 § 6) — embedding & model giả, DB test thật, không cần key."""

import shutil
import uuid

import pytest
from sqlalchemy import func, select

from app.agents.tools import finance_tools
from app.agents.tools.registry import CoachToolContext
from app.ai import embeddings, openai_client
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.coach import SearchKnowledgeOutput
from app.services import coach_evidence, knowledge_service
from tests import coach_dataset
from tests.api.test_coach import _ask, _session, call, result
from tests.coach_dataset import TODAY
from tests.pdf_helper import make_pdf

URL = "/api/v1/knowledge"
KB_DIR = knowledge_service.DEFAULT_KNOWLEDGE_DIR


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    # Vector giả (bag-of-words) cho đoạn dài có độ tương đồng thấp → bỏ ngưỡng thật khi test.
    monkeypatch.setattr(knowledge_service, "MIN_KNOWLEDGE_SCORE", 0.0)


@pytest.fixture
def ingested(db):
    return knowledge_service.ingest_path(db, KB_DIR, embeddings.embed_knowledge)


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- ingest (test case 1, 2) ------------------------------------------------------------------


def test_ingest_six_documents_idempotent(db, ingested):
    """Test case 1: 6 markdown → 6 documents, ≥ 12 chunks; chạy lại không nhân đôi."""
    assert (ingested.documents, ingested.created) == (6, 6)
    assert ingested.chunks >= 12 and not ingested.errors
    assert _count(db, KnowledgeDocument) == 6
    assert _count(db, KnowledgeChunk) == ingested.chunks

    calls = []
    real = openai_client._embed_raw

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    openai_client._embed_raw = spy
    try:
        again = knowledge_service.ingest_path(db, KB_DIR, embeddings.embed_knowledge)
    finally:
        openai_client._embed_raw = real
    assert (again.unchanged, again.created, again.updated) == (6, 0, 0)
    assert calls == []  # không gọi embedding khi nội dung không đổi
    assert _count(db, KnowledgeChunk) == ingested.chunks

    doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source.like("%50-30-20.md")))
    assert doc.source == "knowledge/50-30-20.md" and doc.title == "Quy tắc 50/30/20"
    assert doc.source_type == "markdown" and "budgeting" in doc.meta["tags"]
    chunk = doc.chunks[0]
    assert chunk.meta["source_path"] == doc.source and chunk.meta["language"] == "vi"
    assert chunk.meta["heading_path"] and len(chunk.embedding) == 1536


def test_ingest_update_prune_duplicate(db, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    shutil.copy(KB_DIR / "emergency-fund.md", kb / "a.md")
    shutil.copy(KB_DIR / "debt-basics.md", kb / "b.md")
    first = knowledge_service.ingest_path(db, kb, embeddings.embed_knowledge)
    assert first.created == 2
    assert {d.source for d in db.scalars(select(KnowledgeDocument))} == {"kb/a.md", "kb/b.md"}

    (kb / "a.md").write_text("# Quỹ mới\n\n## Mục\n\nNội dung đã sửa.", encoding="utf-8")
    (kb / "b.md").rename(kb / "c.md")  # đổi tên: cùng nội dung, file cũ không còn
    second = knowledge_service.ingest_path(db, kb, embeddings.embed_knowledge, prune=True)
    assert (second.updated, second.created, second.skipped, second.removed) == (2, 0, 0, 0)
    titles = {d.source: d.title for d in db.scalars(select(KnowledgeDocument))}
    assert set(titles) == {"kb/a.md", "kb/c.md"} and titles["kb/a.md"] == "Quỹ mới"
    renamed = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source == "kb/c.md"))
    assert all(c.meta["source_path"] == "kb/c.md" for c in renamed.chunks)

    (kb / "c.md").unlink()
    third = knowledge_service.ingest_path(db, kb, embeddings.embed_knowledge, prune=True)
    assert (third.unchanged, third.removed) == (1, 1)
    assert {d.source for d in db.scalars(select(KnowledgeDocument))} == {"kb/a.md"}
    assert _count(db, KnowledgeChunk) == 1


def test_duplicate_content_in_other_file_is_skipped(db, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    shutil.copy(KB_DIR / "sinking-funds.md", kb / "one.md")
    shutil.copy(KB_DIR / "sinking-funds.md", kb / "two.md")
    report = knowledge_service.ingest_path(db, kb, embeddings.embed_knowledge)
    assert (report.created, report.skipped) == (1, 1)


def test_ingest_pdf_and_bad_files(db, tmp_path):
    """Test case 2: PDF 3 trang → extract text, chunk có nguồn PDF + số trang."""
    kb = tmp_path / "docs_kb"
    kb.mkdir()
    pages = [
        "Emergency fund basics\nKeep 3 to 6 months of essential costs.",
        "Where to keep it\nA separate savings account.",
        "Refill after use\nRebuild the fund first.",
    ]
    (kb / "guide.pdf").write_bytes(make_pdf(pages, title="Emergency guide"))
    (kb / "broken.pdf").write_bytes(b"%PDF-1.4 broken")
    (kb / "notes.txt").write_text("bỏ qua", encoding="utf-8")
    report = knowledge_service.ingest_path(db, kb, embeddings.embed_knowledge)
    assert report.created == 1 and report.skipped == 1
    assert report.errors and "broken.pdf" in report.errors[0]
    doc = db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.source == "docs_kb/guide.pdf")
    )
    assert doc.source_type == "pdf" and doc.title == "Emergency guide"
    assert doc.chunks[0].meta["pages"] == [1, 2, 3]
    assert "3 to 6 months" in doc.chunks[0].content


def test_ingest_ai_error_raises(db, monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    with pytest.raises(openai_client.AIUnavailable):
        knowledge_service.ingest_path(db, KB_DIR, embeddings.embed_knowledge)


# --- API ---------------------------------------------------------------------------------------


def test_search_endpoint_and_chunk_detail(client, ingested):
    """Test case 3 (embedding giả): 'quỹ khẩn cấp bao nhiêu tháng' → doc quỹ khẩn cấp ở top 3."""
    resp = client.get(f"{URL}/search", params={"q": "quỹ khẩn cấp bao nhiêu tháng", "limit": 3})
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert any(r["source"] == "knowledge/emergency-fund.md" for r in results[:3])
    top = results[0]
    assert top["citation"].startswith(top["title"]) and top["source"] in top["citation"]

    detail = client.get(f"{URL}/chunks/{top['chunk_id']}").json()
    assert detail["content"] == top["content"] and detail["headings"]
    assert client.get(f"{URL}/chunks/{uuid.uuid4()}").status_code == 404

    docs = client.get(f"{URL}/documents").json()["items"]
    assert len(docs) == 6 and sum(d["chunk_count"] for d in docs) == ingested.chunks


def test_search_validation_and_no_key(client, monkeypatch):
    assert client.get(f"{URL}/search", params={"q": ""}).status_code == 422
    assert client.get(f"{URL}/search", params={"q": "x" * 301}).status_code == 422
    assert client.get(f"{URL}/search", params={"q": "x", "limit": 11}).status_code == 422
    assert client.get(f"{URL}/search", params={"q": "  "}).json()["code"] == "empty_query"
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    resp = client.get(f"{URL}/search", params={"q": "50/30/20"})
    assert resp.status_code == 503 and resp.json()["code"] == "AI_NOT_CONFIGURED"


def test_search_empty_knowledge_base(client):
    assert client.get(f"{URL}/search", params={"q": "50/30/20"}).json()["results"] == []


def test_reindex_endpoint_and_path_guard(client):
    resp = client.post(f"{URL}/reindex", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["documents"] == 6 and body["chunks"] >= 12 and body["created"] == 6
    assert client.post(f"{URL}/reindex").json()["unchanged"] == 6
    for path in ("../", "../../Windows", "C:/Windows"):
        bad = client.post(f"{URL}/reindex", json={"path": path})
        assert bad.status_code == 422 and bad.json()["code"] == "invalid_path"
    missing = client.post(f"{URL}/reindex", json={"path": "khong_ton_tai"})
    assert missing.json()["code"] == "path_not_found"


# --- Coach tool + citations (test case 5–7 với model giả) ------------------------------------


def _kb_ctx(db):
    return CoachToolContext(db=db, today=TODAY, embedder=embeddings.embed_queries)


def test_search_knowledge_tool_output(db, ingested):
    ctx = _kb_ctx(db)
    tool = finance_tools.search_knowledge_tool(ctx)
    ctx.recorder.begin("k1", "search_knowledge", {"query": "phương pháp hũ"})
    raw = tool.invoke({"query": "phương pháp 6 chiếc hũ", "limit": 3})
    ctx.recorder.finish("k1", 2, None)
    output = ctx.recorder.ordered()[0].output
    assert isinstance(output, SearchKnowledgeOutput) and len(output.results) == 3
    assert output.results[0].source == "knowledge/envelope-jars.md"
    assert '"citation"' in raw and output.note
    summary, count = coach_evidence.summarize_result(output)
    assert summary.startswith("Đã tra kiến thức: Phương pháp phong bì") and count == 3
    assert coach_evidence.evidence_rows("search_knowledge", output) == []


def _kb_citation(db, source: str) -> str:
    doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source == source))
    chunk = doc.chunks[0]
    return f"{doc.title} — {chunk.heading} ({doc.source})"


def test_coach_answer_with_citations_persisted(client, db, ingested, fake_llm):
    """Test case 5: "50/30/20 là gì?" → câu trả lời có mục Nguồn trỏ tới doc 50/30/20."""
    calls, responses = fake_llm
    cite = _kb_citation(db, "knowledge/50-30-20.md")
    answer = (
        "Quy tắc 50/30/20 chia thu nhập thực nhận thành 50% thiết yếu, 30% mong muốn và 20% "
        f"tiết kiệm. Nếu bạn muốn, bạn có thể thử áp dụng.\n\n**Nguồn:**\n- {cite}"
    )
    responses += [
        result(calls=[call("search_knowledge", {"query": "50/30/20 là gì"}, "k1")]),
        result(answer),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "50/30/20 là gì?").json()
    assert data["guard_status"] == "passed", data["assistant_message"]["metadata"]
    assert data["tool_trace"][0]["result_summary"].startswith("Đã tra kiến thức")
    citations = data["citations"]
    assert citations and citations[0]["source"] == "knowledge/50-30-20.md"
    assert citations[0]["ref"] == "S1" and citations[0]["snippet"]
    assert all(c["source"] == "knowledge/50-30-20.md" for c in citations)
    tool_msg = next(m for m in calls[1]["messages"] if m["role"] == "tool")
    assert "citation" in tool_msg["content"]
    # Lưu cùng message → mở lại session vẫn thấy nguồn.
    detail = client.get(f"/api/v1/coach/sessions/{session['id']}").json()
    assert detail["messages"][-1]["citations"] == citations


def test_guard_requires_sources_and_rejects_fabricated(client, db, ingested, fake_llm):
    calls, responses = fake_llm
    cite = _kb_citation(db, "knowledge/50-30-20.md")
    no_source = "Quy tắc 50/30/20 chia thu nhập thành 3 phần."
    fabricated = f"{no_source}\n\n**Nguồn:**\n- Sách Cha giàu cha nghèo, chương 3"
    good = f"{no_source}\n\n**Nguồn:**\n- {cite}"
    responses += [
        result(calls=[call("search_knowledge", {"query": "50/30/20"}, "k1")]),
        result(no_source),
        result(good),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "50/30/20 là gì?").json()
    assert data["guard_status"] == "rewritten"
    assert any("Nguồn" in p for p in data["assistant_message"]["metadata"]["guard_problems"])
    assert "Nguồn:" in calls[2]["messages"][-1]["content"]  # yêu cầu viết lại nhắc mục Nguồn

    responses += [
        result(calls=[call("search_knowledge", {"query": "50/30/20"}, "k2")]),
        result(fabricated),
        result(fabricated),
    ]
    data = _ask(client, session["id"], "50/30/20 là gì?").json()
    assert data["guard_status"] == "fallback"
    content = data["assistant_message"]["content"]
    assert "Cha giàu" not in content and "Nguồn:" in content
    assert data["citations"]  # fallback liệt kê nguồn thật đã tra


def test_personal_fit_question_forces_data_tool(client, db, ingested, fake_llm):
    """Test case 6: "50/30/20 … có phù hợp với tao không" → phải gọi thêm tool số liệu."""
    coach_dataset.seed_all(db)
    calls, responses = fake_llm
    cite = _kb_citation(db, "knowledge/50-30-20.md")
    kb_only = f"50/30/20 là chia 50% / 30% / 20%.\n\n**Nguồn:**\n- {cite}"
    responses += [
        result(calls=[call("search_knowledge", {"query": "50/30/20"}, "k1")]),
        result(kb_only),
        result(
            calls=[
                call(
                    "get_spending_summary",
                    {
                        "from_date": "2026-09-01",
                        "to_date": "2026-09-30",
                        "group_by": "spending_type",
                    },
                    "s1",
                )
            ]
        ),
        result(kb_only),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "50/30/20 là gì, có phù hợp với tao không?").json()
    names = [t["name"] for t in data["tool_trace"]]
    assert names == ["search_knowledge", "get_spending_summary"]
    assert data["guard_status"] == "rewritten"
    problems = data["assistant_message"]["metadata"]["guard_problems"]
    assert any("phù hợp" in p for p in problems)
    # Tool số liệu trả % thu nhập để so với 50/30/20 mà không phải tự tính.
    summary_msg = [m for m in calls[3]["messages"] if m["role"] == "tool"][-1]
    assert '"income_share_pct"' in summary_msg["content"]
    assert '"net_income_pct"' in summary_msg["content"]


def test_not_found_answer_without_sources_passes(client, ingested, fake_llm):
    """Test case 7: kiến thức không có trong thư viện → nói rõ, không bịa nguồn."""
    _, responses = fake_llm
    responses += [
        result(calls=[call("search_knowledge", {"query": "quy tắc FIRE 4%"}, "k1")]),
        result(
            "Mình chưa tìm thấy nguồn đủ tin cậy trong thư viện kiến thức của app về quy tắc này."
        ),
    ]
    session = _session(client)
    data = _ask(client, session["id"], "Quy tắc FIRE rút 4% là gì?").json()
    assert data["guard_status"] == "passed" and data["citations"] == []
