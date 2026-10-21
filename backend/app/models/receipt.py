import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import RECEIPT_STATUSES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Receipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ảnh hoá đơn user upload (Phase 13).

    `file_path` là đường dẫn tương đối (posix) trong `UPLOAD_DIR`, vd
    `receipts/2026/10/{id}.jpg` — không lưu đường dẫn tuyệt đối. `extracted` = output model vision
    (`ReceiptVisionOutput`), `draft` = `TransactionDraft` dựng từ extraction lúc trích xuất (thành
    `ai_suggestion` của giao dịch khi user xác nhận). Giao dịch chỉ được tạo khi user xác nhận.
    """

    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(RECEIPT_STATUSES)})", name="status"),
        CheckConstraint("file_size_bytes > 0", name="file_size_positive"),
        # (status, created_at): lọc theo trạng thái + mới nhất trước (btree quét ngược).
        Index("ix_receipts_status_created_at", "status", "created_at"),
        Index("ix_receipts_sha256", "sha256"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="uploaded", server_default="uploaded"
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Giao dịch tạo khi user xác nhận; xoá giao dịch → giữ receipt (`confirmed`), bỏ liên kết.
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL", use_alter=True)
    )
