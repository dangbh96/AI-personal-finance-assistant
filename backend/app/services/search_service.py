"""Hybrid semantic search giao dịch (Phase 15) — deterministic, nhận vector query qua `embedder`.

1. Embed câu tìm kiếm đặt trong ngữ cảnh chi tiêu (`QUERY_TEMPLATE`) qua `embedder` (raise
   `AIUnavailable` → router trả 503).
2. Ứng viên = top `limit × 5` theo cosine distance (HNSW) ∪ giao dịch có ghi chú / tên danh mục
   chứa từ khoá (ILIKE) — cùng bộ lọc ngày ở SQL.
3. `score = 0.75 × (1 − distance) + 0.25 × keyword_boost` — boost 1.0 nếu ghi chú chứa cả cụm,
   0.5 nếu tên danh mục chứa cụm, còn lại 0.5 × tỉ lệ từ khoá có trong ghi chú.
4. Tổng tiền tính bằng Python trên kết quả trả về (không nhờ AI).
"""

import re
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.text import strip_accents
from app.models import Transaction
from app.repositories import embedding_repository
from app.schemas.coach import (
    SearchTransactionItem,
    SearchTransactionsInput,
    SearchTransactionsOutput,
)
from app.schemas.search import TransactionSearchResponse, TransactionSearchResult
from app.services.embedding_service import Embedder

SEMANTIC_WEIGHT = 0.75
KEYWORD_WEIGHT = 0.25
CANDIDATE_FACTOR = 5
MAX_KEYWORD_TERMS = 5
# Kết quả chỉ khớp ngữ nghĩa mà độ tương đồng thấp hơn ngưỡng này bị bỏ (nhiễu). Golden Phase 15
# (`text-embedding-3-small`): dòng liên quan ≥ 0.37, dòng không liên quan ~0.21–0.32.
MIN_SEMANTIC_SCORE = 0.3

# Từ chỉ thời gian / từ nối — không dùng làm từ khoá (khoảng ngày đã có bộ lọc riêng).
STOPWORDS = frozenset(
    {
        "thang",
        "nay",
        "truoc",
        "tuan",
        "nam",
        "ngay",
        "hom",
        "qua",
        "cua",
        "cho",
        "va",
        "cac",
        "nhung",
        "khoan",
        "tien",
        "o",
        "la",
        "the",
        "nao",
        "bao",
        "nhieu",
        "toi",
        "tao",
        "minh",
    }
)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize(text: str | None) -> str:
    """Chữ thường, bỏ dấu, chỉ giữ chữ / số: "Cà phê Highlands!" → "ca phe highlands"."""
    if not text:
        return ""
    return _NON_WORD_RE.sub(" ", strip_accents(text).lower()).strip()


def clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


# Câu tìm ngắn ("ăn ngoài") bị model embedding nhỏ hiểu lệch ("ngoài" → đi ra ngoài / đi lại);
# đặt vào ngữ cảnh giao dịch giúp query gần không gian của nội dung đã embed (golden Phase 15:
# precision@10 "ăn ngoài" 0.3 → 0.9, "đi lại" giữ 1.0).
QUERY_TEMPLATE = "Chi tiêu {query}"


def embedding_query_text(query: str) -> str:
    if normalize(query).startswith(("chi tieu", "khoan chi")):
        return query
    return QUERY_TEMPLATE.format(query=query)


def keyword_tokens(query: str) -> list[str]:
    """Từ khoá (đã chuẩn hoá) có nghĩa trong câu tìm kiếm."""
    seen: dict[str, None] = {}
    for token in normalize(query).split():
        if len(token) >= 2 and token not in STOPWORDS:
            seen.setdefault(token)
    return list(seen)


def sql_terms(query: str) -> list[str]:
    """Chuỗi tìm bằng ILIKE: cả cụm + các từ ≥ 3 ký tự (giữ dấu như user gõ)."""
    phrase = clean_query(query)
    terms = [phrase]
    for word in phrase.split():
        word = word.strip(".,;:!?\"'()")
        if (
            len(word) >= 3
            and normalize(word) not in STOPWORDS
            and word.lower() not in (t.lower() for t in terms)
        ):
            terms.append(word)
    return terms[: MAX_KEYWORD_TERMS + 1]


def _contains(needle: str, haystack: str) -> bool:
    """`needle` xuất hiện trong `haystack` bắt đầu ở ranh giới từ ("grab" khớp "grabfood")."""
    if not needle or not haystack:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}", haystack) is not None


def keyword_boost(query: str, note: str | None, category_name: str) -> float:
    phrase = normalize(query)
    note_n = normalize(note)
    if _contains(phrase, note_n):
        return 1.0
    if _contains(phrase, normalize(category_name)):
        return 0.5
    tokens = keyword_tokens(query)
    if not tokens or not note_n:
        return 0.0
    words = set(note_n.split())
    found = sum(1 for t in tokens if t in words)
    return round(0.5 * found / len(tokens), 4)


def combine_score(semantic: float | None, boost: float) -> float:
    return round(SEMANTIC_WEIGHT * (semantic or 0.0) + KEYWORD_WEIGHT * boost, 4)


def _validate(query: str, date_from: date | None, date_to: date | None) -> str:
    cleaned = clean_query(query)
    if not cleaned:
        raise DomainError("Bạn nhập nội dung cần tìm nhé", "empty_query")
    if date_from and date_to and date_from > date_to:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")
    return cleaned


def search_transactions(
    db: Session,
    query: str,
    embedder: Embedder,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
) -> TransactionSearchResponse:
    cleaned = _validate(query, date_from, date_to)
    vector = embedder([embedding_query_text(cleaned)]).vectors[0]
    pool = limit * CANDIDATE_FACTOR

    candidates: dict[object, tuple[Transaction, float | None, bool]] = {}
    for t, distance in embedding_repository.vector_candidates(
        db, vector, date_from=date_from, date_to=date_to, limit=pool
    ):
        candidates[t.id] = (t, 1.0 - distance, True)
    for t, distance in embedding_repository.keyword_candidates(
        db, sql_terms(cleaned), vector, date_from=date_from, date_to=date_to, limit=pool
    ):
        if t.id not in candidates:
            semantic = 1.0 - distance if distance is not None else None
            candidates[t.id] = (t, semantic, False)

    scored: list[TransactionSearchResult] = []
    for t, semantic, from_vector in candidates.values():
        boost = keyword_boost(cleaned, t.note, t.category.name)
        if boost == 0 and (semantic is None or semantic < MIN_SEMANTIC_SCORE):
            continue
        reason = ("hybrid" if from_vector else "keyword") if boost > 0 else "semantic"
        scored.append(
            TransactionSearchResult(
                transaction_id=t.id,
                occurred_on=t.occurred_on,
                note=t.note,
                amount=t.amount,
                direction=t.direction,  # type: ignore[arg-type]
                category_id=t.category_id,
                category_name=t.category.name,
                category_icon=t.category.icon,
                spending_type=t.spending_type,  # type: ignore[arg-type]
                source=t.source,  # type: ignore[arg-type]
                score=combine_score(semantic, boost),
                semantic_score=round(semantic, 4) if semantic is not None else None,
                keyword_boost=boost,
                match_reason=reason,  # type: ignore[arg-type]
            )
        )
    scored.sort(key=lambda r: (-r.score, -r.occurred_on.toordinal(), str(r.transaction_id)))
    results = scored[:limit]
    income = sum(r.amount for r in results if r.direction == "income")
    expense = sum(r.amount for r in results if r.direction == "expense")
    return TransactionSearchResponse(
        query=cleaned,
        from_date=date_from,
        to_date=date_to,
        limit=limit,
        result_count=len(results),
        total_amount=expense,
        income_total=income,
        expense_total=expense,
        net=income - expense,
        missing_embedding_count=embedding_repository.count_missing(db, date_from, date_to),
        results=results,
    )


def search_for_coach(
    db: Session, data: SearchTransactionsInput, embedder: Embedder
) -> SearchTransactionsOutput:
    """Tool Coach `search_transactions` (chỉ đọc): kết quả rút gọn + tổng thu / chi."""
    response = search_transactions(
        db,
        data.query,
        embedder,
        date_from=data.from_date,
        date_to=data.to_date,
        limit=data.limit,
    )
    return SearchTransactionsOutput(
        query=response.query,
        from_date=response.from_date,
        to_date=response.to_date,
        result_count=response.result_count,
        expense_total=response.expense_total,
        income_total=response.income_total,
        items=[
            SearchTransactionItem(
                occurred_on=r.occurred_on,
                note=r.note,
                category_name=r.category_name,
                amount=r.amount,
                direction=r.direction,
                match_reason=r.match_reason,
            )
            for r in response.results
        ],
        note=(
            "Kết quả xếp theo độ liên quan và có thể lẫn giao dịch không liên quan — chỉ dùng "
            "các dòng khớp câu hỏi; expense_total / income_total là tổng của mọi dòng trả về."
            if response.results
            else "Không tìm thấy giao dịch phù hợp."
        ),
    )
