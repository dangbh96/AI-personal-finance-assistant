"""Embedding giao dịch cho semantic search (Phase 15) — phần deterministic.

- `build_transaction_embedding_content`: chuỗi đưa đi embed (ghi chú đã làm sạch + danh mục +
  khoảng tiền + loại chi tiêu). Không embed số tiền chính xác / số tài khoản.
- `embed_transactions`: tạo / cập nhật embedding cho giao dịch thiếu hoặc đã cũ (nội dung / model
  đổi) qua `embedder` do caller truyền vào (`ai/embeddings`, vì `services` không import `ai`).
- `embed_transactions_best_effort`: dùng sau khi giao dịch đã commit; lỗi chỉ log, không raise.
- `backfill`: duyệt toàn bộ giao dịch theo lô.
"""

import logging
import re
import unicodedata
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.models import Transaction
from app.repositories import embedding_repository

logger = logging.getLogger(__name__)

MAX_NOTE_CHARS = 300
DEFAULT_BATCH_SIZE = 100
# Số giao dịch tối đa embed đồng bộ trong 1 request (vd commit import); phần còn lại → backfill.
MAX_INLINE_EMBED = 500

SPENDING_TYPE_TEXT = {
    "essential": "thiết yếu",
    "non_essential": "không thiết yếu",
    "irregular": "bất thường",
}
_SPACE_RE = re.compile(r"\s+")
_NUMBER_TOKEN_RE = re.compile(r"\S*\d\S*")


@dataclass(frozen=True)
class EmbeddedTexts:
    vectors: list[list[float]]
    model: str


Embedder = Callable[[list[str]], EmbeddedTexts]


@dataclass(frozen=True)
class EmbedOutcome:
    processed: int
    unchanged: int


def current_model() -> str:
    return get_settings().openai_embedding_model


def amount_bucket(amount: int) -> str:
    """Khoảng tiền (không dùng số chính xác để giảm nhiễu, vẫn tìm được "khoản lớn")."""
    if amount < 100_000:
        return "<100k"
    if amount < 500_000:
        return "100k-500k"
    if amount < 2_000_000:
        return "500k-2m"
    if amount < 10_000_000:
        return "2m-10m"
    return ">10m"


def clean_note(note: str | None) -> str:
    """Làm sạch ghi chú trước khi embed: bỏ token có ≥ 5 chữ số (số tài khoản, mã giao dịch),
    gọn khoảng trắng, ghi chú sao kê VIẾT HOA → chữ thường; ≤ 300 ký tự."""
    if not note:
        return ""

    def drop_long_numbers(match: re.Match[str]) -> str:
        token = match.group(0)
        return "" if sum(ch.isdigit() for ch in token) >= 5 else token

    text = _NUMBER_TOKEN_RE.sub(drop_long_numbers, unicodedata.normalize("NFC", note))
    text = _SPACE_RE.sub(" ", text).strip(" .,-:;/#")
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
        text = text.lower()
        text = text[:1].upper() + text[1:]
    return text[:MAX_NOTE_CHARS].strip()


def build_transaction_embedding_content(transaction: Transaction) -> str:
    """`"{note}. Danh mục: {category}. Khoản {bucket}. Loại: {spending_type | thu nhập}."`"""
    category = transaction.category
    kind = (
        "thu nhập"
        if transaction.direction == "income"
        else SPENDING_TYPE_TEXT.get(transaction.spending_type or "", "chi tiêu")
    )
    parts = []
    note = clean_note(transaction.note)
    if note:
        parts.append(f"{note}.")
    parts.append(f"Danh mục: {category.name}.")
    parts.append(f"Khoản {amount_bucket(transaction.amount)}.")
    parts.append(f"Loại: {kind}.")
    return " ".join(parts)


def stale_transactions(db: Session, transactions: Sequence[Transaction]) -> list[Transaction]:
    """Giao dịch chưa có embedding hoặc embedding không khớp nội dung / model hiện tại."""
    model = current_model()
    states = embedding_repository.embedding_states(db, [t.id for t in transactions])
    return [
        t
        for t in transactions
        if states.get(t.id) != (build_transaction_embedding_content(t), model)
    ]


def embed_transactions(
    db: Session,
    transactions: Sequence[Transaction],
    embedder: Embedder,
    *,
    force: bool = False,
) -> EmbedOutcome:
    """Embed giao dịch thiếu / cũ (nội dung hoặc model khác) rồi commit. Lỗi AI → raise."""
    if not transactions:
        return EmbedOutcome(0, 0)
    model = current_model()
    contents = {t.id: build_transaction_embedding_content(t) for t in transactions}
    states = embedding_repository.embedding_states(db, list(contents))
    todo = [
        tid for tid, content in contents.items() if force or states.get(tid) != (content, model)
    ]
    if not todo:
        return EmbedOutcome(0, len(contents))
    embedded = embedder([contents[tid] for tid in todo])
    if len(embedded.vectors) != len(todo):
        raise DomainError("Dịch vụ embedding trả thiếu kết quả", "embedding_mismatch")
    for tid, vector in zip(todo, embedded.vectors, strict=True):
        embedding_repository.upsert(db, tid, vector, contents[tid], model)
    db.commit()
    return EmbedOutcome(len(todo), len(contents) - len(todo))


def import_batch_transaction_ids(db: Session, batch_id: uuid.UUID) -> list[uuid.UUID]:
    return embedding_repository.import_batch_transaction_ids(db, batch_id)


def embed_transactions_best_effort(
    db: Session, transaction_ids: Sequence[uuid.UUID], embedder: Embedder
) -> int:
    """Embed sau khi giao dịch đã lưu. Không bao giờ raise: lỗi AI / DB chỉ log (giao dịch vẫn
    được lưu, `backfill_embeddings` sẽ bổ sung sau). Trả số giao dịch đã embed."""
    ids = list(dict.fromkeys(transaction_ids))[:MAX_INLINE_EMBED]
    if not ids:
        return 0
    try:
        transactions = embedding_repository.transactions_by_ids(db, ids)
        return embed_transactions(db, transactions, embedder).processed
    except Exception as exc:  # noqa: BLE001 — best-effort, không chặn lưu giao dịch
        db.rollback()
        code = getattr(exc, "code", type(exc).__name__)
        level = logging.DEBUG if code == "AI_NOT_CONFIGURED" else logging.WARNING
        logger.log(level, "embedding best_effort skipped count=%d error=%s", len(ids), code)
        return 0


@dataclass(frozen=True)
class BackfillReport:
    scanned: int
    processed: int
    unchanged: int
    remaining_missing: int


def backfill(
    db: Session,
    embedder: Embedder,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    transaction_ids: Sequence[uuid.UUID] | None = None,
    force: bool = False,
    on_batch: Callable[[int, int], None] | None = None,
) -> BackfillReport:
    """Embed mọi giao dịch thiếu / cũ (hoặc chỉ `transaction_ids`), tối đa `limit` giao dịch được
    embed. Lỗi AI → raise (dừng ở lô hiện tại; các lô trước đã commit)."""
    if batch_size < 1:
        raise DomainError("batch_size phải ≥ 1", "invalid_batch_size")
    scanned = processed = unchanged = 0

    def run(batch: Sequence[Transaction]) -> None:
        nonlocal scanned, processed, unchanged
        scanned += len(batch)
        if limit is not None:
            remaining = limit - processed
            if remaining <= 0:
                return
            todo = list(batch) if force else stale_transactions(db, batch)
            unchanged += len(batch) - len(todo)
            batch = todo[:remaining]
        outcome = embed_transactions(db, batch, embedder, force=force)
        processed += outcome.processed
        unchanged += outcome.unchanged
        if on_batch:
            on_batch(scanned, processed)

    if transaction_ids is not None:
        ids = list(dict.fromkeys(transaction_ids))
        for start in range(0, len(ids), batch_size):
            run(embedding_repository.transactions_by_ids(db, ids[start : start + batch_size]))
    else:
        after: uuid.UUID | None = None
        while True:
            page = embedding_repository.transactions_page(db, after_id=after, limit=batch_size)
            if not page:
                break
            run(page)
            after = page[-1].id
            if limit is not None and processed >= limit:
                break
    return BackfillReport(
        scanned=scanned,
        processed=processed,
        unchanged=unchanged,
        remaining_missing=embedding_repository.count_missing(db),
    )
