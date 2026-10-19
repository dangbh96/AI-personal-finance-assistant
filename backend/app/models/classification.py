import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.category import Category
from app.models.enums import SPENDING_TYPES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

_SPENDING_TYPE_CHECK = f"IN ({sql_in(SPENDING_TYPES)})"


class ClassificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cách user muốn phân loại một loại món: pattern đã chuẩn hoá → category × spending_type.

    Mỗi pattern chỉ có 1 preference (user đổi ý thì cập nhật). Ràng buộc `spending_type` theo
    `category.kind` kiểm tra ở `classification_preference_service`.
    """

    __tablename__ = "classification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "pattern", postgresql_nulls_not_distinct=True),
        CheckConstraint(
            f"spending_type IS NULL OR spending_type {_SPENDING_TYPE_CHECK}", name="spending_type"
        ),
        CheckConstraint("hit_count >= 0", name="hit_count_non_negative"),
        CheckConstraint("length(pattern) >= 2", name="pattern_length"),
        Index("ix_classification_preferences_pattern", "pattern"),
        Index("ix_classification_preferences_last_used_at", text("last_used_at DESC")),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    example_text: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    spending_type: Mapped[str | None] = mapped_column(Text)
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)


class ClassificationFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một lần user sửa đề xuất phân loại của AI trước khi lưu giao dịch."""

    __tablename__ = "classification_feedback"
    __table_args__ = (
        CheckConstraint(
            f"ai_spending_type IS NULL OR ai_spending_type {_SPENDING_TYPE_CHECK}",
            name="ai_spending_type",
        ),
        CheckConstraint(
            f"final_spending_type IS NULL OR final_spending_type {_SPENDING_TYPE_CHECK}",
            name="final_spending_type",
        ),
        Index("ix_classification_feedback_transaction_id", "transaction_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    ai_category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="SET NULL")
    )
    ai_spending_type: Mapped[str | None] = mapped_column(Text)
    final_category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    final_spending_type: Mapped[str | None] = mapped_column(Text)
