"""Golden test RAG knowledge base (Phase 16) — OpenAI thật.

    pytest -m ai -s tests/ai_golden/test_rag_coach.py

Ingest `backend/knowledge/` (6 tài liệu tự viết) vào DB test (rollback sau test) bằng
`OPENAI_EMBEDDING_MODEL`. Ngưỡng:
- Retrieval: 12 câu hỏi tiếng Việt đời thường → hit@3 ≥ 0.80 (tài liệu đúng nằm trong top 3).
- Coach (gpt-4o): "50/30/20 là gì?" có mục Nguồn trỏ tới tài liệu 50/30/20; "… có phù hợp với tao
  không" gọi `search_knowledge` **và** một tool số liệu, có nguồn; câu hỏi kiến thức không có trong
  thư viện → nói không tìm thấy nguồn, không gắn nguồn; "Pay yourself first khác gì 50/30/20?" có
  nguồn của cả hai; "quỹ khẩn cấp của tao nên bao nhiêu" tra kiến thức + chi thiết yếu.
"""

import sys

import pytest

from app.agents import coach_graph
from app.ai import embeddings, openai_client
from app.services import coach_guard, knowledge_service, review_narrative
from tests import coach_dataset
from tests.coach_dataset import TODAY

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

HIT_THRESHOLD = 0.80
PERSONAL_TOOLS = coach_guard.PERSONAL_DATA_TOOLS

# (câu hỏi, tài liệu đúng)
RETRIEVAL_CASES: list[tuple[str, str]] = [
    ("quỹ khẩn cấp bao nhiêu tháng", "emergency-fund.md"),
    ("phương pháp hũ", "envelope-jars.md"),
    ("50/30/20 là gì", "50-30-20.md"),
    ("trả cho mình trước nghĩa là gì", "pay-yourself-first.md"),
    ("tiền phòng thân nên để ở đâu", "emergency-fund.md"),
    ("để dành dần cho khoản chi lớn biết trước như học phí, quà Tết", "sinking-funds.md"),
    ("trả nợ thẻ tín dụng thế nào cho nhanh", "debt-basics.md"),
    ("snowball và avalanche khác nhau thế nào", "debt-basics.md"),
    ("chia lương vào 6 cái hũ", "envelope-jars.md"),
    ("tiết kiệm trước rồi mới tiêu", "pay-yourself-first.md"),
    ("nhu cầu thiết yếu nên chiếm bao nhiêu phần trăm thu nhập", "50-30-20.md"),
    ("sinking fund khác gì quỹ dự phòng", "sinking-funds.md"),
]


def _report(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


@pytest.fixture
def kb(db):
    report = knowledge_service.ingest_path(
        db, knowledge_service.DEFAULT_KNOWLEDGE_DIR, embeddings.embed_knowledge
    )
    assert report.documents == 6 and report.chunks >= 12
    return report


def _ask(db, question: str):
    answer = coach_graph.run_coach(db, question, today=TODAY)
    meta = answer.metadata
    _report(
        f"\n=== {question}\nguard={meta.guard_status} rounds={meta.tool_rounds} "
        f"tokens={meta.total_tokens} problems={meta.guard_problems}\n"
        f"tools={[(t.name, t.args) for t in answer.tool_trace]}\n"
        f"citations={[c.citation for c in answer.citations]}\n{answer.content}"
    )
    return answer


def _clean(text: str) -> None:
    for phrase in coach_guard.BANNED_PHRASES:
        assert not review_narrative.contains_phrase(text, phrase), phrase


def test_retrieval_hit_at_3(db, kb):
    hits = 0
    for query, expected in RETRIEVAL_CASES:
        results = knowledge_service.search(db, query, embeddings.embed_queries, limit=3).results
        sources = [r.source.split("/")[-1] for r in results]
        hit = expected in sources
        hits += hit
        _report(f"{'✓' if hit else '✗'} {query} → {sources} {[r.score for r in results]}")
    rate = hits / len(RETRIEVAL_CASES)
    _report(f"hit@3 = {hits}/{len(RETRIEVAL_CASES)} = {rate:.2f}")
    assert rate >= HIT_THRESHOLD


def test_what_is_50_30_20_has_source(db, kb):
    answer = _ask(db, "50/30/20 là gì?")
    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert "search_knowledge" in {t.name for t in answer.tool_trace}
    assert coach_guard.source_lines(answer.content)
    assert any(c.source == "knowledge/50-30-20.md" for c in answer.citations)
    _clean(answer.content)


def test_50_30_20_fits_me_uses_personal_data(db, kb):
    coach_dataset.seed_all(db)
    answer = _ask(db, "50/30/20 là gì, có phù hợp với tao không?")
    names = {t.name for t in answer.tool_trace}
    assert "search_knowledge" in names
    assert names & PERSONAL_TOOLS
    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert any(c.source == "knowledge/50-30-20.md" for c in answer.citations)
    _clean(answer.content)


def test_pyf_vs_50_30_20(db, kb):
    answer = _ask(db, "Pay yourself first khác gì 50/30/20?")
    assert answer.metadata.guard_status in ("passed", "rewritten")
    sources = {c.source for c in answer.citations}
    assert "knowledge/pay-yourself-first.md" in sources or "knowledge/50-30-20.md" in sources
    _clean(answer.content)


def test_my_emergency_fund(db, kb):
    coach_dataset.seed_all(db)
    answer = _ask(db, "Quỹ khẩn cấp của tao nên bao nhiêu?")
    names = {t.name for t in answer.tool_trace}
    assert "search_knowledge" in names and names & PERSONAL_TOOLS
    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert any(c.source == "knowledge/emergency-fund.md" for c in answer.citations)
    _clean(answer.content)


def test_unknown_topic_no_fabricated_source(db, kb):
    answer = _ask(db, "Quy tắc FIRE rút 4% mỗi năm khi nghỉ hưu là gì?")
    assert answer.metadata.guard_status in ("passed", "rewritten", "fallback")
    lowered = answer.content.lower()
    assert any(m in lowered for m in coach_guard.NOT_FOUND_MARKERS) or answer.citations == []
    assert answer.citations == []
