"""Phase 16: đọc markdown / PDF, chia đoạn, guard nguồn kiến thức (không cần DB / AI)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR
from app.core.errors import DomainError
from app.services import coach_guard
from app.services.knowledge_chunking import (
    MAX_TOKENS,
    OVERLAP_TOKENS,
    chunk_document,
    citation,
    embedding_text,
    estimate_tokens,
    load_document,
    load_markdown,
    load_pdf,
)
from tests.pdf_helper import make_pdf

KB_DIR = BACKEND_DIR / "knowledge"
EXPECTED_DOCS = {
    "50-30-20.md",
    "envelope-jars.md",
    "pay-yourself-first.md",
    "emergency-fund.md",
    "sinking-funds.md",
    "debt-basics.md",
}


def _sentences(n: int, word: str = "câu") -> str:
    return " ".join(
        f"Đây là {word} số {i} nói về ngân sách cá nhân và tiết kiệm." for i in range(n)
    )


def test_estimate_tokens_and_citation():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("a" * 2400) == 800
    assert citation("Quy tắc 50/30/20", "Cách áp dụng", "knowledge/50-30-20.md") == (
        "Quy tắc 50/30/20 — Cách áp dụng (knowledge/50-30-20.md)"
    )
    assert citation("Tài liệu", None, "x.pdf") == "Tài liệu (x.pdf)"


def test_markdown_front_matter_title_and_headings():
    raw = (
        "---\ntitle: Quỹ khẩn cấp\ntags: saving, quỹ\n---\n\n# Tiêu đề H1\n\nMở đầu.\n\n"
        "## Bao nhiêu tháng?\n\n3–6 tháng chi phí.\n\n### Chi tiết\n\n- dòng 1\n- dòng 2\n"
    ).encode()
    doc = load_markdown(raw, fallback_title="x")
    assert doc.title == "Quỹ khẩn cấp"  # front matter ưu tiên hơn H1
    assert doc.metadata["tags"] == ["saving", "quỹ"]
    texts = [(b.text, b.heading_path, b.section_start) for b in doc.blocks]
    assert texts[0] == ("Mở đầu.", (), True)
    assert texts[1] == ("3–6 tháng chi phí.", ("Bao nhiêu tháng?",), True)
    assert texts[2] == ("- dòng 1\n- dòng 2", ("Bao nhiêu tháng?", "Chi tiết"), True)


def test_markdown_title_fallbacks():
    assert load_markdown(b"# H1 title\n\nabc", fallback_title="f").title == "H1 title"
    assert load_markdown(b"abc", fallback_title="f").title == "f"
    with pytest.raises(DomainError) as exc:
        load_markdown(b"\xff\xfe\xfa", fallback_title="f")
    assert exc.value.code == "invalid_encoding"


def test_knowledge_base_files_chunk_within_limits():
    """Test case 1 (phần thuần): 6 tài liệu tự viết → ≥ 12 đoạn, mỗi đoạn ≤ 800 token ước lượng."""
    files = sorted(KB_DIR.glob("*.md"))
    assert {f.name for f in files} == EXPECTED_DOCS
    total = 0
    for file in files:
        doc = load_document(file)
        chunks = chunk_document(doc)
        assert doc.title and doc.metadata["language"] == "vi"
        assert all(c.tokens <= MAX_TOKENS for c in chunks)
        assert [c.index for c in chunks] == list(range(len(chunks)))
        assert all(c.heading for c in chunks)
        assert all(c.headings and c.heading == c.headings[0] for c in chunks)
        total += len(chunks)
    assert total >= 12


def test_long_section_splits_with_overlap():
    raw = f"# Doc\n\n## Mục dài\n\n{_sentences(120)}\n".encode()
    chunks = chunk_document(load_markdown(raw, fallback_title="d"))
    assert len(chunks) >= 3
    assert all(c.tokens <= MAX_TOKENS for c in chunks)
    assert all(c.heading == "Mục dài" for c in chunks)
    # Đoạn sau bắt đầu bằng phần cuối (~100 token) của đoạn trước.
    head = chunks[1].content.split("\n\n")[0]
    assert head and chunks[0].content.endswith(head)
    assert estimate_tokens(head) <= OVERLAP_TOKENS + 25


def test_sections_break_at_heading_when_big_enough():
    body = "\n\n".join(f"## Mục {i}\n\n{_sentences(27, f'ý {i}')}" for i in range(3))
    chunks = chunk_document(load_markdown(f"# D\n\n{body}".encode(), fallback_title="d"))
    # Mỗi mục ~530 token ≥ 500 → cắt đúng ranh giới mục, không overlap.
    assert [c.heading for c in chunks] == ["Mục 0", "Mục 1", "Mục 2"]
    assert chunks[1].content.startswith("Đây là ý 1 số 0")


def test_small_sections_are_packed_together():
    body = "\n\n".join(f"## Mục {i}\n\n{_sentences(18, f'ý {i}')}" for i in range(3))
    chunks = chunk_document(load_markdown(f"# D\n\n{body}".encode(), fallback_title="d"))
    # Mục ~350 token < 500 → gộp tới khi đủ lớn rồi mới cắt ở ranh giới mục kế tiếp.
    assert [c.headings for c in chunks] == [["Mục 0", "Mục 1"], ["Mục 2"]]


def test_tiny_tail_merged_into_previous():
    raw = f"# D\n\n## A\n\n{_sentences(14)}\n\n## B\n\nNgắn.".encode()
    chunks = chunk_document(load_markdown(raw, fallback_title="d"))
    assert len(chunks) == 1
    assert chunks[0].headings == ["A", "B"]


def test_embedding_text_has_title_and_path():
    raw = b"# T\n\n## A\n\n### B\n\nNoi dung."
    chunk = chunk_document(load_markdown(raw, fallback_title="d"))[0]
    assert embedding_text("T", chunk).startswith("T › A › B\n\nNoi dung.")


def test_pdf_three_pages():
    """Test case 2: PDF 3 trang qua pypdf → text + nguồn PDF theo trang."""
    pages = [
        "Emergency fund basics\nKeep 3 to 6 months of essential costs.",
        "Where to keep it\nA separate savings account that is easy to withdraw.",
        "Refill after use\nRebuild the fund before other goals.",
    ]
    doc = load_pdf(make_pdf(pages, title="Emergency fund PDF"), fallback_title="f")
    assert doc.title == "Emergency fund PDF" and doc.source_type == "pdf"
    assert doc.metadata["page_count"] == 3
    assert {b.page for b in doc.blocks} == {1, 2, 3}
    assert "3 to 6 months" in " ".join(b.text for b in doc.blocks)
    chunks = chunk_document(doc)
    assert chunks[0].pages == [1, 2, 3] and chunks[0].heading == "Trang 1"


def test_pdf_errors():
    with pytest.raises(DomainError) as exc:
        load_pdf(b"not a pdf", fallback_title="f")
    assert exc.value.code == "unreadable_pdf"
    with pytest.raises(DomainError) as exc:
        load_pdf(make_pdf([""]), fallback_title="f")
    assert exc.value.code == "empty_pdf"
    with pytest.raises(DomainError) as exc:
        load_document(Path("notes.txt"), b"x")
    assert exc.value.code == "unsupported_file_type"
    assert load_document(Path("x.pdf"), make_pdf(["Hello"])).title == "x"


# ---------- guard nguồn / dữ liệu cá nhân ----------

TITLES = ["Quy tắc 50/30/20", "Quỹ khẩn cấp (quỹ dự phòng)"]
SOURCES = ["knowledge/50-30-20.md", "knowledge/emergency-fund.md"]


def test_source_lines_parsing():
    answer = "Giải thích.\n\n**Nguồn:**\n- Quy tắc 50/30/20 — Cách áp dụng (x)\n- B\n\nHết."
    assert coach_guard.source_lines(answer) == ["Quy tắc 50/30/20 — Cách áp dụng (x)", "B"]
    assert coach_guard.source_lines("Nguồn: Quy tắc 50/30/20") == ["Quy tắc 50/30/20"]
    assert coach_guard.source_lines("Không có nguồn ở đây") is None


def test_check_citations():
    ok = (
        "50/30/20 chia thu nhập.\n\n"
        "Nguồn:\n- Quy tắc 50/30/20 — Cách áp dụng (knowledge/50-30-20.md)"
    )
    assert coach_guard.check_citations(ok, TITLES, SOURCES) == []
    by_path = "…\n\nNguồn:\n- knowledge/emergency-fund.md"
    assert coach_guard.check_citations(by_path, TITLES, SOURCES) == []
    missing = coach_guard.check_citations("50/30/20 chia thu nhập.", TITLES, SOURCES)
    assert missing and "thiếu mục" in missing[0]
    fake = "…\n\nNguồn:\n- Sách Cha giàu cha nghèo"
    assert "không có trong kết quả" in coach_guard.check_citations(fake, TITLES, SOURCES)[0]
    not_found = "Mình chưa tìm thấy nguồn đủ tin cậy trong thư viện kiến thức của app."
    assert coach_guard.check_citations(not_found, TITLES, SOURCES) == []
    # Không có kết quả tra cứu mà vẫn ghi nguồn → bịa nguồn.
    assert coach_guard.check_citations(ok, [], [])


def test_cited_indexes():
    answer = "x\n\n**Nguồn:**\n- Quỹ khẩn cấp (quỹ dự phòng) — Bao nhiêu tháng (k)"
    assert coach_guard.cited_indexes(answer, TITLES, SOURCES) == [1]
    assert coach_guard.cited_indexes("không có", TITLES, SOURCES) == []


@pytest.mark.parametrize(
    ("question", "personal"),
    [
        ("50/30/20 là gì, có phù hợp với tao không?", True),
        ("Quỹ khẩn cấp của tao nên bao nhiêu?", True),
        ("Tôi nên áp dụng phương pháp hũ không?", True),
        ("50/30/20 là gì?", False),
        ("Pay yourself first khác gì 50/30/20?", False),
    ],
)
def test_personal_question_requires_data_tool(question, personal):
    assert coach_guard.is_personal_question(question) is personal
    only_kb = coach_guard.check_tool_usage(question, ["search_knowledge"])
    assert bool(only_kb) is personal
    assert (
        coach_guard.check_tool_usage(question, ["search_knowledge", "get_spending_summary"]) == []
    )
    assert coach_guard.check_tool_usage(question, ["get_budget_status"]) == []


def test_knowledge_numbers_are_allowed():
    payload = {"results": [{"content": "Giữ 3–6 tháng, ví dụ 27.000.000 đồng; tỉ lệ 60/20/20."}]}
    allowed = coach_guard.allowed_numbers([payload], "50/30/20?", date(2026, 10, 22))
    assert {Decimal(27_000_000), Decimal(60), Decimal(20), Decimal(50)} <= allowed


def test_fallback_with_citations_passes_guard():
    cites = ["Quy tắc 50/30/20 — Cách áp dụng (knowledge/50-30-20.md)"]
    text = coach_guard.fallback_answer([], cites)
    allowed = coach_guard.allowed_numbers([{"citation": cites[0]}], "", date(2026, 10, 22))
    assert coach_guard.check_answer(text, allowed) == []
    assert coach_guard.check_citations(text, TITLES, SOURCES) == []
