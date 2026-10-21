import uuid
from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.budget import BudgetAllocation
from app.models.enums import ADVICE_STATUSES, ADVICE_VERDICTS, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BudgetAdvice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tư vấn điều chỉnh cho 1 dòng phân bổ của tháng `month` (Phase 8).

    `verdict` + `evidence` do `services/advisor_rules` tính (deterministic); `explanation` là văn
    bản (AI hoặc template) diễn giải evidence, `narrative` giữ 3 tầng của nó. Mỗi
    `(budget_allocation_id, month)` có tối đa 1 advice `open` (unique index một phần).
    """

    __tablename__ = "budget_advice"
    __table_args__ = (
        CheckConstraint("extract(day from month) = 1", name="month_first_day"),
        CheckConstraint(f"verdict IN ({sql_in(ADVICE_VERDICTS)})", name="verdict"),
        CheckConstraint(f"status IN ({sql_in(ADVICE_STATUSES)})", name="status"),
        Index(
            "uq_budget_advice_open_allocation_month",
            "budget_allocation_id",
            "month",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_budget_advice_month", "month"),
        Index("ix_budget_advice_budget_allocation_id", "budget_allocation_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    budget_allocation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("budget_allocations.id", ondelete="CASCADE"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    applied_month: Mapped[date | None] = mapped_column(Date)
    dismiss_reason: Mapped[str | None] = mapped_column(Text)

    allocation: Mapped[BudgetAllocation] = relationship(lazy="joined", innerjoin=True)
