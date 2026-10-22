"""Truy vấn `transaction_embeddings` + pgvector (Phase 15). Mọi tham số đều bind qua ORM."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionEmbedding

# HNSW mặc định chỉ xét `ef_search = 40` ứng viên rồi mới lọc ngày → có thể trả thiếu kết quả.
# pgvector ≥ 0.8: quét lặp tới khi đủ LIMIT sau khi lọc.
HNSW_EF_SEARCH = 100


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _date_filter(stmt: Select, date_from: date | None, date_to: date | None) -> Select:
    if date_from is not None:
        stmt = stmt.where(Transaction.occurred_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.occurred_on <= date_to)
    return stmt


def get(db: Session, transaction_id: uuid.UUID) -> TransactionEmbedding | None:
    return db.get(TransactionEmbedding, transaction_id)


def upsert(
    db: Session, transaction_id: uuid.UUID, embedding: Sequence[float], content: str, model: str
) -> None:
    stmt = insert(TransactionEmbedding).values(
        transaction_id=transaction_id,
        embedding=list(embedding),
        content=content,
        model=model,
        embedded_at=func.clock_timestamp(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[TransactionEmbedding.transaction_id],
        set_={
            "embedding": stmt.excluded.embedding,
            "content": stmt.excluded.content,
            "model": stmt.excluded.model,
            "embedded_at": func.clock_timestamp(),
        },
    )
    db.execute(stmt)


def embedding_states(
    db: Session, transaction_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str]]:
    """`{transaction_id: (content, model)}` của các giao dịch đã có embedding."""
    if not transaction_ids:
        return {}
    rows = db.execute(
        select(
            TransactionEmbedding.transaction_id,
            TransactionEmbedding.content,
            TransactionEmbedding.model,
        ).where(TransactionEmbedding.transaction_id.in_(list(transaction_ids)))
    )
    return {tid: (content, model) for tid, content, model in rows}


def transactions_page(db: Session, *, after_id: uuid.UUID | None, limit: int) -> list[Transaction]:
    """Giao dịch theo id tăng dần (keyset) — để backfill duyệt toàn bộ bảng."""
    stmt = select(Transaction).order_by(Transaction.id).limit(limit)
    if after_id is not None:
        stmt = stmt.where(Transaction.id > after_id)
    return list(db.scalars(stmt).unique())


def transactions_by_ids(db: Session, ids: Sequence[uuid.UUID]) -> list[Transaction]:
    if not ids:
        return []
    return list(db.scalars(select(Transaction).where(Transaction.id.in_(list(ids)))).unique())


def import_batch_transaction_ids(db: Session, batch_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Transaction.id)
            .where(Transaction.import_batch_id == batch_id)
            .order_by(Transaction.occurred_on, Transaction.id)
        )
    )


def count_missing(db: Session, date_from: date | None = None, date_to: date | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(Transaction)
        .outerjoin(TransactionEmbedding, TransactionEmbedding.transaction_id == Transaction.id)
        .where(TransactionEmbedding.transaction_id.is_(None))
    )
    return int(db.scalar(_date_filter(stmt, date_from, date_to)) or 0)


def count_all(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(TransactionEmbedding)) or 0)


def vector_candidates(
    db: Session,
    vector: Sequence[float],
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[tuple[Transaction, float]]:
    """Top `limit` giao dịch gần `vector` nhất (cosine distance `<=>`, dùng HNSW index)."""
    db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = TransactionEmbedding.embedding.cosine_distance(list(vector)).label("distance")
    stmt = (
        select(Transaction, distance)
        .join(TransactionEmbedding, TransactionEmbedding.transaction_id == Transaction.id)
        .order_by(distance)
        .limit(limit)
    )
    rows = db.execute(_date_filter(stmt, date_from, date_to)).unique().all()
    return [(t, float(d)) for t, d in rows]


def keyword_candidates(
    db: Session,
    terms: Sequence[str],
    vector: Sequence[float],
    *,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[tuple[Transaction, float | None]]:
    """Giao dịch có ghi chú hoặc tên danh mục chứa một trong `terms` (ILIKE), kèm distance nếu
    đã embed (null nếu chưa)."""
    conds = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        conds.append(Transaction.note.ilike(pattern, escape="\\"))
        conds.append(Category.name.ilike(pattern, escape="\\"))
    if not conds:
        return []
    distance = TransactionEmbedding.embedding.cosine_distance(list(vector)).label("distance")
    stmt = (
        select(Transaction, distance)
        .join(Category, Category.id == Transaction.category_id)
        .outerjoin(TransactionEmbedding, TransactionEmbedding.transaction_id == Transaction.id)
        .where(or_(*conds))
        .order_by(Transaction.occurred_on.desc(), Transaction.id)
        .limit(limit)
    )
    rows = db.execute(_date_filter(stmt, date_from, date_to)).unique().all()
    return [(t, float(d) if d is not None else None) for t, d in rows]
