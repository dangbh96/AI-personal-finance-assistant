"""Truy vấn `knowledge_documents` / `knowledge_chunks` (Phase 16)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument

HNSW_EF_SEARCH = 100


def get_by_source(db: Session, source: str) -> KnowledgeDocument | None:
    return db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source == source))


def get_by_hash(db: Session, content_hash: str) -> KnowledgeDocument | None:
    return db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
    )


def get_chunk(db: Session, chunk_id: uuid.UUID) -> KnowledgeChunk | None:
    return db.get(KnowledgeChunk, chunk_id)


def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.source)))


def chunk_counts(db: Session) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(KnowledgeChunk.document_id, func.count()).group_by(KnowledgeChunk.document_id)
    )
    return {doc_id: int(n) for doc_id, n in rows}


def add(db: Session, document: KnowledgeDocument) -> KnowledgeDocument:
    db.add(document)
    db.flush()
    return document


def delete_document(db: Session, document: KnowledgeDocument) -> None:
    """Xoá tài liệu (chunk bị xoá theo FK CASCADE)."""
    db.delete(document)
    db.flush()


def count_chunks(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0)


def nearest_chunks(
    db: Session, vector: Sequence[float], *, limit: int
) -> list[tuple[KnowledgeChunk, float]]:
    """Top `limit` chunk gần `vector` nhất (cosine distance, HNSW)."""
    db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
    distance = KnowledgeChunk.embedding.cosine_distance(list(vector)).label("distance")
    rows = db.execute(
        select(KnowledgeChunk, distance).order_by(distance, KnowledgeChunk.id).limit(limit)
    ).all()
    return [(chunk, float(d)) for chunk, d in rows]
