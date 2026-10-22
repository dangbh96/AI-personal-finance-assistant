import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.embedding import EMBEDDING_DIMENSIONS
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

KNOWLEDGE_SOURCE_TYPES = ("markdown", "pdf")


class KnowledgeDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một tài liệu kiến thức tài chính đã ingest (Phase 16). Ingest lại theo `content_hash`."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("source_type IN ('markdown', 'pdf')", name="source_type"),
        Index("ix_knowledge_documents_source", "source", unique=True),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Đường dẫn file gốc (posix, tương đối thư mục `backend/` nếu nằm trong đó).
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # `metadata` là tên dành riêng của SQLAlchemy declarative → thuộc tính Python là `meta`.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        order_by="KnowledgeChunk.chunk_index",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một đoạn (~500–800 token ước lượng) của tài liệu kèm embedding."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks", lazy="joined")
