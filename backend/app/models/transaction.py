import uuid
from datetime import date
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.category import Category
from app.models.enums import DIRECTIONS, SPENDING_TYPES, TRANSACTION_SOURCES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"direction IN ({sql_in(DIRECTIONS)})", name="direction"),
        CheckConstraint(
            f"spending_type IS NULL OR spending_type IN ({sql_in(SPENDING_TYPES)})",
            name="spending_type",
        ),
        CheckConstraint(f"source IN ({sql_in(TRANSACTION_SOURCES)})", name="source"),
        CheckConstraint(
            "(direction = 'income' AND spending_type IS NULL)"
            " OR (direction = 'expense' AND spending_type IS NOT NULL)",
            name="direction_spending_type",
        ),
        Index("ix_transactions_occurred_on", "occurred_on"),
        Index("ix_transactions_category_id_occurred_on", "category_id", "occurred_on"),
        Index("ix_transactions_recurring_id", "recurring_id"),
        Index("ix_transactions_receipt_id", "receipt_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    spending_type: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, default="manual", server_default="manual"
    )
    raw_input: Mapped[str | None] = mapped_column(Text)
    ai_suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Phase 12: giao dịch tạo từ khoản định kỳ (`source = 'recurring'`) hoặc đã được gắn khi user
    # xác nhận đề xuất phát hiện định kỳ. Khoản định kỳ chỉ bị tắt, không xoá (SET NULL phòng hờ).
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recurring_transactions.id", ondelete="SET NULL")
    )
    # Phase 13: giao dịch tạo từ ảnh hoá đơn user đã xác nhận (`source = 'receipt'`).
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("receipts.id", ondelete="SET NULL")
    )

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)
