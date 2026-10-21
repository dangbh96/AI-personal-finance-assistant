import uuid
from datetime import date

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import GOAL_STATUSES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.transaction import Transaction


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mục tiêu tiết kiệm (Phase 11). Không lưu `current_amount` — luôn tính bằng tổng
    `goal_contributions.amount` (`goal_service`)."""

    __tablename__ = "goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="target_amount_positive"),
        CheckConstraint("priority > 0", name="priority_positive"),
        CheckConstraint(f"status IN ({sql_in(GOAL_STATUSES)})", name="status"),
        Index("ix_goals_status_priority", "status", "priority"),
        Index("ix_goals_deadline", "deadline"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    target_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )

    contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", passive_deletes=True
    )


class GoalContribution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một khoản góp vào goal. `income_transaction_id` = thu nhập đã cấp tiền (luồng PYF);
    NULL = khoản góp thủ công (vd số tiền đã có sẵn). Xoá giao dịch thu nhập → giữ khoản góp,
    bỏ liên kết (`SET NULL`)."""

    __tablename__ = "goal_contributions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_goal_contributions_goal_id_contributed_on", "goal_id", "contributed_on"),
        Index("ix_goal_contributions_income_transaction_id", "income_transaction_id"),
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    income_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contributed_on: Mapped[date] = mapped_column(Date, nullable=False)

    goal: Mapped[Goal] = relationship(back_populates="contributions")
    income_transaction: Mapped[Transaction | None] = relationship(lazy="joined")
