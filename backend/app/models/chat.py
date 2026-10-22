import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import CHAT_ROLES, sql_in
from app.models.mixins import UUIDPrimaryKeyMixin


def _utcnow() -> datetime:
    # Giờ phía Python (không phải `now()` của transaction) để các message ghi trong cùng một
    # transaction vẫn có thứ tự, và session được đẩy lên đầu danh sách khi có message mới.
    return datetime.now(UTC)


class _ChatTimestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )


class ChatSession(UUIDPrimaryKeyMixin, _ChatTimestamps, Base):
    """Một cuộc trò chuyện với Financial Coach (Phase 10)."""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_updated_at", "updated_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        order_by="ChatMessage.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(UUIDPrimaryKeyMixin, _ChatTimestamps, Base):
    """Một message trong session. Assistant message giữ tool trace (`tool_calls`), bảng
    "Dữ liệu đã dùng" (`evidence`) và metadata model / token / chi phí / guard."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(f"role IN ({sql_in(CHAT_ROLES)})", name="role"),
        Index("ix_chat_messages_session_id_created_at", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    evidence: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Phase 16: nguồn kiến thức (chunk RAG) câu trả lời đã trích.
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # `metadata` là tên dành riêng của SQLAlchemy declarative → thuộc tính Python là `meta`.
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
