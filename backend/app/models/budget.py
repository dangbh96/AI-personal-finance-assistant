import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
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
from app.models.enums import (
    ALLOCATION_GROUPS,
    BUDGET_STATUSES,
    BUDGET_STRATEGIES,
    ZONE_MODES,
    sql_in,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ngân sách 1 tháng (1 budget / tháng). `savings_target` = tổng planned nhóm `savings`,
    do `budget_service` đồng bộ khi lưu."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("period_month"),
        CheckConstraint("extract(day from period_month) = 1", name="period_month_first_day"),
        CheckConstraint(f"strategy IN ({sql_in(BUDGET_STRATEGIES)})", name="strategy"),
        CheckConstraint(f"status IN ({sql_in(BUDGET_STATUSES)})", name="status"),
        CheckConstraint("expected_income >= 0", name="expected_income_non_negative"),
        CheckConstraint(
            "savings_target IS NULL OR savings_target >= 0", name="savings_target_non_negative"
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    expected_income: Mapped[int] = mapped_column(BigInteger, nullable=False)
    savings_target: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="draft", server_default="draft"
    )

    allocations: Mapped[list["BudgetAllocation"]] = relationship(
        back_populates="budget",
        cascade="all, delete-orphan",
        order_by="BudgetAllocation.position",
        lazy="selectin",
    )


class BudgetAllocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một dòng phân bổ: theo danh mục (`category_id`) **hoặc** theo hũ / nhóm (`jar_name`).

    Cách dòng `jar_name` khớp giao dịch phụ thuộc `budgets.strategy` — xem
    `budget_service.allocation_scope`.

    Vùng linh hoạt (Phase 9, `zone_service`): `zone_mode = manual` → user nhập đủ 3 ngưỡng;
    `auto` → ngưỡng là cache do `zone_service` tính (NULL = chưa tính). Ràng buộc
    `comfort_low <= comfort_high <= warning_threshold` kiểm ở service.
    """

    __tablename__ = "budget_allocations"
    __table_args__ = (
        CheckConstraint(f'"group" IN ({sql_in(ALLOCATION_GROUPS)})', name="group"),
        CheckConstraint("planned_amount >= 0", name="planned_amount_non_negative"),
        CheckConstraint(
            "(category_id IS NOT NULL) <> (jar_name IS NOT NULL)", name="category_xor_jar"
        ),
        CheckConstraint(f"zone_mode IN ({sql_in(ZONE_MODES)})", name="zone_mode"),
        Index("ix_budget_allocations_budget_id", "budget_id"),
        Index("ix_budget_allocations_category_id", "category_id"),
    )

    budget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    group: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("categories.id", ondelete="RESTRICT")
    )
    jar_name: Mapped[str | None] = mapped_column(Text)
    planned_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    comfort_low: Mapped[int | None] = mapped_column(BigInteger)
    comfort_high: Mapped[int | None] = mapped_column(BigInteger)
    warning_threshold: Mapped[int | None] = mapped_column(BigInteger)
    zone_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="auto", server_default="auto"
    )

    budget: Mapped[Budget] = relationship(back_populates="allocations")
    category: Mapped[Category | None] = relationship(lazy="joined")
