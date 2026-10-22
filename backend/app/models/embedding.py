import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

EMBEDDING_DIMENSIONS = 1536


class TransactionEmbedding(Base):
    """Vector ngữ nghĩa của 1 giao dịch (Phase 15). Xoá giao dịch → xoá embedding (CASCADE)."""

    __tablename__ = "transaction_embeddings"
    __table_args__ = (
        Index(
            "ix_transaction_embeddings_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    # Chuỗi đã embed — so sánh để biết embedding còn khớp giao dịch hay đã cũ.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
