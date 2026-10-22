"""`response_guard` của Financial Coach (Phase 10) — deterministic, không gọi AI (ADR-005).

- `classify_request`: câu hỏi ngoài phạm vi (đầu tư / chứng khoán / crypto / thuế) hoặc yêu cầu
  Coach tự ghi dữ liệu → trả lời bằng template, không gọi model.
- `allowed_numbers`: tập số câu trả lời được phép dùng = số trong output các tool đã gọi (bỏ ID)
  + số trong câu hỏi + ngày hôm nay + số nhỏ 0–12 (số tháng, đánh số ý).
- `check_answer`: số ⊆ allowed, không cụm từ phán xét / ra lệnh / tự nhận đã sửa dữ liệu, không lộ
  tên kỹ thuật, câu trả lời có số liệu phải đủ "Quan sát" → "Vì sao" → gợi ý có điều kiện.
- `fallback_answer`: khi model vẫn sai sau 1 lần viết lại → liệt kê evidence (luôn qua guard).
"""

import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.coach import EvidenceItem
from app.services import advice_narrative, review_narrative
from app.services.money import format_vnd
from app.services.review_narrative import extract_numbers, strip_ids

REFUSED_OUT_OF_SCOPE = "refused_out_of_scope"
REFUSED_WRITE_REQUEST = "refused_write_request"

# So khớp có dấu (NFC, chữ thường): bỏ dấu sẽ trùng từ thường ("thuế" ↔ "thuê nhà",
# "quỹ mở" ↔ "quy mô", "tạo" ↔ "tao"). Dạng không dấu chỉ thêm khi không gây nhầm.
OUT_OF_SCOPE_TERMS: tuple[str, ...] = (
    "cổ phiếu",
    "co phieu",
    "chứng khoán",
    "chung khoan",
    "crypto",
    "bitcoin",
    "btc",
    "ethereum",
    "coin",
    "nft",
    "tiền ảo",
    "tien ao",
    "tiền điện tử",
    "tiền mã hoá",
    "tiền mã hóa",
    "đầu tư",
    "dau tu",
    "trái phiếu",
    "trai phieu",
    "quỹ mở",
    "chứng chỉ quỹ",
    "forex",
    "ngoại hối",
    "thuế",
    "tncn",
)
WRITE_VERBS: tuple[str, ...] = (
    "thêm",
    "tạo",
    "xoá",
    "xóa",
    "sửa",
    "cập nhật",
    "đổi",
    "giảm",
    "tăng",
    "đặt",
    "chỉnh",
    "điều chỉnh",
    "ghi",
    "nhập",
    "huỷ",
    "hủy",
    "chấp nhận",
    "áp dụng",
    "bỏ qua",
    "lưu",
)
WRITE_OBJECTS: dict[str, str] = {
    "giao dịch": "/transactions",
    "khoản chi": "/transactions",
    "khoản thu": "/transactions",
    "ngân sách": "/budget",
    "budget": "/budget",
    "hạn mức": "/budget",
    "vùng": "/budget",
    "tư vấn": "/budget/advice",
    "danh mục": "/settings",
    "mục tiêu": "/goals",
    "khoản góp": "/goals",
}
WRITE_MARKERS: tuple[str, ...] = (
    "giúp",
    "hộ",
    "dùm",
    "giùm",
    "cho tao",
    "cho tôi",
    "cho mình",
    "cho em",
    "tự",
    "luôn đi",
)
# Câu hỏi để xem / cân nhắc ("Có nên tăng ngân sách ăn uống không?") không phải yêu cầu ghi.
READ_INTENTS: tuple[str, ...] = (
    "xem",
    "nên",
    "có nên",
    "kiểm tra",
    "phân tích",
    "cho biết",
    "bao nhiêu",
    "nào",
    "sao",
    "thế nào",
    "không",
)
LINK_LABELS: dict[str, str] = {
    "/transactions": "Giao dịch",
    "/budget": "Ngân sách",
    "/budget/advice": "Tư vấn ngân sách",
    "/settings": "Cài đặt",
    "/goals": "Mục tiêu",
}

# Giọng văn (ai-architecture.md § 2) + cấm ra lệnh / tự nhận đã thay đổi dữ liệu (read-only).
BANNED_PHRASES: tuple[str, ...] = (
    *review_narrative.BANNED_PHRASES,
    "ngay lập tức",
    "bạn cần phải",
    "bắt buộc phải",
    "sai lầm",
    *advice_narrative.CLAIMED_ACTIONS,
    "mình đã điều chỉnh",
    "mình đã cập nhật",
    "mình đã thay đổi",
    "mình đã tạo",
    "mình đã xoá",
    "đã giảm ngân sách",
)
RECOMMEND_MARKERS: tuple[str, ...] = ("nên", "gợi ý", "khuyên", "hãy", "đề xuất")
SECTION_OBSERVATION = "quan sát"
SECTION_WHY = "vì sao"
SMALL_NUMBERS = frozenset(Decimal(n) for n in range(13))
TEXT_NUMBER_KEYS = frozenset({"content", "title", "heading", "citation"})
_TECHNICAL_NAME_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
# Link nội bộ (/budget/advice?month=2026-10-01) không phải số liệu.
_LINK_RE = re.compile(r"(?<![\w/])(?:https?://\S+|/[a-z][\w/\-]*(?:\?[\w=&\-.%]*)?)")
_MONTH_KEY_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _nfc(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _starts_with_verb(text: str) -> bool:
    words = re.sub(r"^[^\w]+", "", text)
    return any(re.match(rf"{re.escape(v)}(?!\w)", words) for v in WRITE_VERBS)


def classify_request(question: str) -> str | None:
    """`refused_out_of_scope` / `refused_write_request` / `None` (Coach trả lời bình thường)."""
    text = _nfc(question)
    if any(_has_term(text, t) for t in OUT_OF_SCOPE_TERMS):
        return REFUSED_OUT_OF_SCOPE
    has_verb = any(_has_term(text, v) for v in WRITE_VERBS)
    has_object = any(_has_term(text, o) for o in WRITE_OBJECTS)
    reading = any(_has_term(text, r) for r in READ_INTENTS)
    if (
        has_verb
        and has_object
        and not reading
        and (any(_has_term(text, m) for m in WRITE_MARKERS) or _starts_with_verb(text))
    ):
        return REFUSED_WRITE_REQUEST
    return None


def write_request_links(question: str) -> list[str]:
    text = _nfc(question)
    links = list(dict.fromkeys(path for o, path in WRITE_OBJECTS.items() if _has_term(text, o)))
    if "/budget" in links and "/budget/advice" not in links:
        links.append("/budget/advice")
    return links or ["/budget", "/budget/advice"]


def refusal_answer(kind: str, question: str) -> str:
    if kind == REFUSED_OUT_OF_SCOPE:
        return (
            "Mình chỉ hỗ trợ các câu hỏi về thu chi, ngân sách và review trong app — không tư vấn "
            "đầu tư, chứng khoán, crypto hay thuế.\n\n"
            "Bạn có thể hỏi, ví dụ: “Tháng này khoản nào vượt budget?”, “Tao nên giảm khoản "
            "nào?” hoặc “Có khoản bất thường nào không?”."
        )
    links = " hoặc ".join(f"[{LINK_LABELS[p]}]({p})" for p in write_request_links(question))
    return (
        "Coach chỉ đọc dữ liệu nên không tự thay đổi giao dịch, ngân sách hay mục tiêu của bạn.\n\n"
        f"Nếu bạn muốn điều chỉnh, bạn có thể mở {links} để tự thực hiện và xác nhận. "
        "Mình có thể giúp bạn xem số liệu trước khi quyết định — ví dụ “Tháng này khoản nào "
        "vượt budget?”."
    )


# ---------- số được phép ----------


def _collect_keys(node: Any, out: set[Decimal]) -> None:
    """Khoá dạng YYYY-MM (vd `totals_by_month`) cũng là số liệu ngày tháng; số trong văn bản kiến
    thức (`content`, `title`, `heading`, `citation` — Phase 16, vd "50/30/20", "3–6 tháng") được
    phép trích."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and (m := _MONTH_KEY_RE.match(key)):
                out.update(Decimal(int(p)) for p in m.groups())
            if key in TEXT_NUMBER_KEYS and isinstance(value, str):
                out.update(abs(v) for _, v in extract_numbers(value))
            _collect_keys(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_keys(value, out)


def allowed_numbers(tool_payloads: Iterable[Any], question: str, today: date) -> set[Decimal]:
    out: set[Decimal] = set(SMALL_NUMBERS)
    for payload in tool_payloads:
        clean = strip_ids(payload)
        out |= review_narrative.collect_numbers(clean)
        _collect_keys(clean, out)
    out.update(v for _, v in extract_numbers(question))
    out.update(Decimal(p) for p in (today.day, today.month, today.year))
    return out


def _without_links(text: str) -> str:
    return _LINK_RE.sub(" ", text)


def _plain(text: str) -> str:
    """Bỏ định dạng markdown đơn giản để so khớp cụm từ."""
    return re.sub(r"[*_`#>]", " ", text)


def _is_year(value: Decimal) -> bool:
    return value == value.to_integral() and 1900 <= value <= 2100


# ---------- kiểm tra ----------


def check_answer(answer: str, allowed: set[Decimal]) -> list[str]:
    """Danh sách vấn đề (rỗng = hợp lệ)."""
    if not answer.strip():
        return ["câu trả lời đang trống"]
    problems: list[str] = []
    text = _without_links(answer)
    plain = _plain(text)

    for phrase in BANNED_PHRASES:
        if review_narrative.contains_phrase(plain, phrase):
            problems.append(f"có cụm từ không được dùng: “{phrase}”")
    if technical := sorted(set(_TECHNICAL_NAME_RE.findall(text))):
        problems.append(
            f"có tên trường / tool kỹ thuật {', '.join(technical)} — hãy viết tiếng Việt"
        )

    numbers = extract_numbers(text)
    invented = [raw for raw, value in numbers if value not in allowed]
    if invented:
        problems.append(
            "có số không nằm trong kết quả tool: "
            + ", ".join(f"“{raw}”" for raw in dict.fromkeys(invented))
            + " — chỉ dùng số copy từ kết quả tool (gọi thêm tool nếu cần)"
        )

    has_data = any(value >= 1000 and not _is_year(value) for _, value in numbers)
    if has_data:
        if not review_narrative.contains_phrase(plain, SECTION_OBSERVATION):
            problems.append("thiếu phần “Quan sát” (số liệu từ tool)")
        if not review_narrative.contains_phrase(plain, SECTION_WHY):
            problems.append("thiếu phần “Vì sao” (giải thích dựa trên dữ liệu)")
        if not review_narrative.has_conditional(plain):
            problems.append("thiếu gợi ý có điều kiện (“Bạn có thể cân nhắc…”, “nếu bạn muốn…”)")
    elif any(review_narrative.contains_phrase(plain, m) for m in RECOMMEND_MARKERS) and not (
        review_narrative.has_conditional(plain)
    ):
        problems.append("khuyến nghị phải có điều kiện (“có thể”, “nếu bạn muốn”, “cân nhắc”)")
    return problems


# ---------- kiến thức & nguồn (Phase 16) ----------

KNOWLEDGE_TOOL = "search_knowledge"
# Tool đọc số liệu của chính người dùng.
PERSONAL_DATA_TOOLS = frozenset(
    {
        "get_spending_summary",
        "get_budget_status",
        "get_category_trend",
        "get_budget_advice",
        "get_recent_reviews",
        "get_goals",
        "search_transactions",
    }
)
_PRONOUNS = ("tao", "tôi", "mình", "em", "tớ")
# Câu hỏi về mức độ phù hợp / áp dụng cho chính người hỏi → phải xem số liệu cá nhân.
PERSONAL_FIT_PATTERNS: tuple[str, ...] = (
    *(f"phù hợp với {p}" for p in _PRONOUNS),
    *(f"hợp với {p}" for p in _PRONOUNS),
    *(f"của {p}" for p in _PRONOUNS),
    *(f"{p} nên" for p in _PRONOUNS),
    *(f"{p} có nên" for p in _PRONOUNS),
    *(f"{p} cần" for p in _PRONOUNS),
    *(f"áp dụng cho {p}" for p in _PRONOUNS),
    *(f"với {p}" for p in _PRONOUNS),
)
NOT_FOUND_MARKERS: tuple[str, ...] = (
    "không tìm thấy nguồn",
    "chưa tìm thấy nguồn",
    "không có nguồn",
    "chưa có nguồn",
    "không tìm thấy thông tin",
    "chưa có thông tin",
    "thư viện kiến thức chưa có",
)
_SOURCE_HEADER_RE = re.compile(r"^[\s>*_#-]*nguồn[\s*_]*:?[\s*_]*(.*)$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def is_personal_question(question: str) -> bool:
    text = _nfc(question)
    return any(_has_term(text, p) for p in PERSONAL_FIT_PATTERNS)


def check_tool_usage(question: str, tool_names: Iterable[str]) -> list[str]:
    """Đã tra kiến thức cho câu hỏi "có phù hợp với tao không" → bắt buộc có tool số liệu."""
    names = set(tool_names)
    if (
        KNOWLEDGE_TOOL in names
        and is_personal_question(question)
        and not names & PERSONAL_DATA_TOOLS
    ):
        return [
            "câu hỏi hỏi mức độ phù hợp với chính người dùng nhưng chưa xem số liệu của họ — "
            "hãy gọi thêm tool số liệu (vd chi tiêu theo loại Thiết yếu / Không thiết yếu "
            "của tháng đã trọn gần nhất) rồi so sánh với kiến thức"
        ]
    return []


def source_lines(answer: str) -> list[str] | None:
    """Các dòng trong mục "Nguồn:" (None = không có mục này)."""
    lines = answer.splitlines()
    for i, line in enumerate(lines):
        match = _SOURCE_HEADER_RE.match(line)
        if not match:
            continue
        found = [match.group(1).strip(" *_")] if match.group(1).strip(" *_") else []
        for rest in lines[i + 1 :]:
            if not rest.strip():
                if found:
                    break
                continue
            if not _BULLET_RE.match(rest) and found:
                break
            found.append(_BULLET_RE.sub("", rest).strip(" *_"))
        return [f for f in found if f]
    return None


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^\w/.-]+", " ", _nfc(text)).split())


def cited_indexes(answer: str, titles: list[str], sources: list[str]) -> list[int]:
    """Vị trí các đoạn kiến thức được nhắc trong mục Nguồn — khớp theo tiêu đề hoặc đường dẫn."""
    lines = [_key(line) for line in source_lines(answer) or []]
    out = []
    for i, (title, source) in enumerate(zip(titles, sources, strict=True)):
        keys = [k for k in (_key(title), _key(source)) if k]
        if any(k in line for line in lines for k in keys):
            out.append(i)
    return out


def check_citations(answer: str, titles: list[str], sources: list[str]) -> list[str]:
    """Đã gọi `search_knowledge`: có kết quả → phải có mục Nguồn và mọi nguồn phải nằm trong kết
    quả (không bịa nguồn); không có kết quả / không dùng được → nói rõ, không ghi nguồn."""
    plain = _nfc(_plain(answer))
    not_found = any(m in plain for m in NOT_FOUND_MARKERS)
    lines = source_lines(answer)
    known = [k for k in (*map(_key, titles), *map(_key, sources)) if k]
    problems: list[str] = []
    if lines is None or not lines:
        if titles and not not_found:
            problems.append(
                "thiếu mục “Nguồn:” — liệt kê citation của các đoạn kiến thức đã dùng (hoặc nói rõ "
                "không tìm thấy nguồn đủ tin cậy)"
            )
        return problems
    for line in lines:
        if not any(k in _key(line) for k in known):
            problems.append(
                f"nguồn “{line}” không có trong kết quả tra cứu — chỉ ghi citation được trả về"
            )
    return problems


# ---------- fallback ----------

MAX_FALLBACK_ROWS = 8


def fallback_answer(evidence: list[EvidenceItem], citations: list[str] | None = None) -> str:
    """Câu trả lời không dùng AI, chỉ liệt kê số liệu đã đọc (luôn qua `check_answer`); có tra
    kiến thức → kèm mục Nguồn để người dùng tự đọc."""
    sources = ["", "**Nguồn:**", *(f"- {c}" for c in dict.fromkeys(citations))] if citations else []
    if not evidence:
        if citations:
            return "\n".join(
                [
                    "Mình chưa tóm tắt được chắc chắn nội dung cho câu hỏi này. Bạn có thể đọc "
                    "trực tiếp các đoạn kiến thức liên quan bên dưới.",
                    *sources,
                ]
            )
        return (
            "Mình chưa diễn giải được câu hỏi này một cách chắc chắn từ dữ liệu hiện có.\n\n"
            "Bạn có thể hỏi cụ thể hơn, ví dụ “Tháng này khoản nào vượt budget?” hoặc xem trực "
            "tiếp ở [Ngân sách](/budget)."
        )
    lines = [
        f"- {e.label} ({e.period}) · {e.metric}: {format_vnd(e.amount)}"
        for e in evidence[:MAX_FALLBACK_ROWS]
    ]
    return "\n".join(
        [
            "**Quan sát**",
            *lines,
            "",
            "**Vì sao**",
            "Đây là số liệu đọc trực tiếp từ dữ liệu của bạn; mình chưa diễn giải được chắc chắn "
            "nên chỉ liệt kê để bạn tự xem.",
            "",
            "**Bạn có thể cân nhắc**",
            "Nếu bạn muốn xem chi tiết, bạn có thể mở [Ngân sách](/budget) hoặc "
            "[Tư vấn ngân sách](/budget/advice).",
            *sources,
        ]
    )


# ---------- tiêu đề session ----------

TITLE_MAX_WORDS = 8
_LEADING_PRONOUNS = ("tao", "tôi", "mình", "em", "anh", "chị", "cho hỏi", "cho mình hỏi")


def make_title(question: str, max_length: int = 60) -> str:
    """ "Tao nên giảm khoản nào?" → "Nên giảm khoản nào"."""
    text = " ".join(unicodedata.normalize("NFC", question).split()).strip(" ?!.…")
    lowered = text.lower()
    for pronoun in sorted(_LEADING_PRONOUNS, key=len, reverse=True):
        if lowered.startswith(pronoun + " "):
            text = text[len(pronoun) + 1 :]
            break
    words = text.split()[:TITLE_MAX_WORDS]
    title = " ".join(words)[:max_length].strip(" ,;:")
    return (title[:1].upper() + title[1:]) if title else "Cuộc trò chuyện mới"
