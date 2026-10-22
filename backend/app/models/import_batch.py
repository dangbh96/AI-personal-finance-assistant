import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import IMPORT_BATCH_STATUSES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Một lần import sao kê CSV / XLSX (Phase 14).

    Preview lưu tạm trong batch (chưa tạo giao dịch): `source_rows` = bảng thô đọc từ file (để
    đổi mapping mà không cần upload lại), `rows` = các dòng preview đã chuẩn hoá + đề xuất phân
    loại. Giao dịch chỉ được tạo ở bước commit khi user xác nhận (`status` → `committed`).
    `file_hash` (sha256 nội dung file) UNIQUE: file đã commit thì không import lại được.
    """

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(IMPORT_BATCH_STATUSES)})", name="status"),
        CheckConstraint(
            "row_count >= 0 AND valid_count >= 0 AND duplicate_count >= 0 AND bad_count >= 0"
            " AND committed_count >= 0",
            name="counts_non_negative",
        ),
        Index("ix_import_batches_created_at", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    bank_name: Mapped[str | None] = mapped_column(Text)
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    date_format: Mapped[str | None] = mapped_column(Text)
    decimal_style: Mapped[str | None] = mapped_column(Text)
    mapping_source: Mapped[str | None] = mapped_column(Text)
    file_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_rows: Mapped[list[Any] | None] = mapped_column(JSONB)
    rows: Mapped[list[Any] | None] = mapped_column(JSONB)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    bad_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    committed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="previewed", server_default="previewed"
    )
    model: Mapped[str | None] = mapped_column(Text)
    ai_error_code: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportMappingProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mapping cột đã dùng cho một ngân hàng + bộ tiêu đề cột (Phase 14).

    `bank_name` = '' khi user không nhập tên ngân hàng; `headers_hash` = sha256 tiêu đề cột đã
    chuẩn hoá. Lưu / cập nhật khi user commit một lô import.
    """

    __tablename__ = "import_mapping_profiles"
    __table_args__ = (UniqueConstraint("bank_name", "headers_hash"),)

    bank_name: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    headers_hash: Mapped[str] = mapped_column(Text, nullable=False)
    headers: Mapped[list[Any] | None] = mapped_column(JSONB)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    date_format: Mapped[str | None] = mapped_column(Text)
    decimal_style: Mapped[str | None] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
