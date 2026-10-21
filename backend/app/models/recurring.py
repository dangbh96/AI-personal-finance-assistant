import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.category import Category
from app.models.enums import DIRECTIONS, RECURRING_FREQUENCIES, SPENDING_TYPES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RecurringTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Khoản định kỳ (Phase 12): lương, tiền nhà, internet… `next_due_on` = kỳ kế tiếp chưa ghi
    thành giao dịch. Lịch: `weekly` dùng `day_of_week` (ISO, Thứ Hai = 1); `monthly` dùng
    `day_of_month` (31 → ngày cuối tháng ở tháng ngắn); `yearly` dùng tháng của `next_due_on` +
    `day_of_month` (29/02 → 28/02 năm không nhuận)."""

    __tablename__ = "recurring_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"direction IN ({sql_in(DIRECTIONS)})", name="direction"),
        CheckConstraint(
            f"spending_type IS NULL OR spending_type IN ({sql_in(SPENDING_TYPES)})",
            name="spending_type",
        ),
        CheckConstraint(
            "(direction = 'income' AND spending_type IS NULL)"
            " OR (direction = 'expense' AND spending_type IS NOT NULL)",
            name="direction_spending_type",
        ),
        CheckConstraint(f"frequency IN ({sql_in(RECURRING_FREQUENCIES)})", name="frequency"),
        CheckConstraint(
            "(frequency = 'weekly' AND day_of_week BETWEEN 1 AND 7 AND day_of_month IS NULL)"
            " OR (frequency IN ('monthly', 'yearly') AND day_of_month BETWEEN 1 AND 31"
            " AND day_of_week IS NULL)",
            name="schedule",
        ),
        Index("ix_recurring_transactions_active_next_due_on", "active", "next_due_on"),
        Index("ix_recurring_transactions_category_id", "category_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    spending_type: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    day_of_month: Mapped[int | None] = mapped_column(Integer)
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    next_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    auto_detected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)
