import uuid
from typing import Any

from sqlalchemy import Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Kịch bản what-if user đặt tên (Phase 17). Chỉ lưu tham số + kết quả mô phỏng lúc lưu —
    không đụng tới giao dịch / ngân sách / mục tiêu thật."""

    __tablename__ = "scenarios"
    __table_args__ = (Index("ix_scenarios_created_at", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
