import uuid
from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import REVIEW_KINDS, REVIEW_STATUSES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WeeklyReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Review 1 tuần (Thứ Hai → Chủ Nhật). `metrics` là số liệu deterministic (kèm highlights),
    `narrative` là văn bản AI (hoặc template dự phòng) đã qua kiểm tra."""

    __tablename__ = "weekly_reviews"
    __table_args__ = (
        UniqueConstraint("week_start"),
        CheckConstraint("extract(isodow from week_start) = 1", name="week_start_monday"),
        CheckConstraint(f"status IN ({sql_in(REVIEW_STATUSES)})", name="status"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="generated", server_default="generated"
    )


class MonthlyReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Review 1 tháng (`month` = ngày 1). Cùng cấu trúc với `WeeklyReview`; `metrics` có thêm
    tiết kiệm, tỉ lệ theo spending_type, khoản bất thường, budget vs actual, nhìn lại các tuần."""

    __tablename__ = "monthly_reviews"
    __table_args__ = (
        UniqueConstraint("month"),
        CheckConstraint("extract(day from month) = 1", name="month_first_day"),
        CheckConstraint(f"status IN ({sql_in(REVIEW_STATUSES)})", name="status"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="generated", server_default="generated"
    )


class ReflectionAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Câu trả lời nhìn lại của user cho một review (weekly — Phase 6, monthly — Phase 7).

    `review_id` trỏ tới `weekly_reviews` hoặc `monthly_reviews` tuỳ `review_kind` nên không có FK.
    """

    __tablename__ = "reflection_answers"
    __table_args__ = (
        CheckConstraint(f"review_kind IN ({sql_in(REVIEW_KINDS)})", name="review_kind"),
        Index("ix_reflection_answers_review_kind_review_id", "review_kind", "review_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    review_kind: Mapped[str] = mapped_column(Text, nullable=False)
    review_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    flagged_transaction_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list, server_default=text("'{}'")
    )
