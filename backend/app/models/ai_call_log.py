import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class AICallLog(UUIDPrimaryKeyMixin, Base):
    """Một lời gọi OpenAI (Phase 18): tác vụ, model, token, chi phí ước tính, latency, kết quả.

    Không lưu prompt / nội dung / API key. Ghi best-effort từ `core/ai_usage`.
    """

    __tablename__ = "ai_call_logs"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error')", name="status"),
        Index("ix_ai_call_logs_created_at", "created_at"),
        Index("ix_ai_call_logs_task_created_at", "task", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="chat")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_estimate_vnd: Mapped[int | None] = mapped_column(BigInteger)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
