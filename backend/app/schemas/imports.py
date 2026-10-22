"""Schema import sao kê CSV / Excel (Phase 14).

Preview / đổi mapping chỉ trả draft (lưu tạm trong `import_batches`), không tạo giao dịch. Giao dịch
chỉ được tạo ở `POST /imports/{id}/commit` sau khi user kiểm tra / sửa preview.
"""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import Direction, ImportBatchStatus, ImportRowStatus, SpendingType
from app.schemas.ai import ClassificationSuggestion
from app.schemas.transaction import Note

DateFormat = Literal["dd/mm/yyyy", "mm/dd/yyyy", "yyyy-mm-dd"]
# `dot_thousands`: 1.500.000 (hoặc 1.500.000,50) — kiểu Việt Nam; `comma_thousands`: 1,500,000.00
DecimalStyle = Literal["dot_thousands", "comma_thousands"]
MappingSource = Literal["guess", "profile", "user"]
SuggestionSource = Literal["preference", "ai", "fallback"]
MAX_COMMIT_ROWS = 5000

BankName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ColumnName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ColumnMapping(BaseModel):
    """Cột trong file (theo tên tiêu đề) → trường chuẩn. Cần `date`, `description` và `amount`
    **hoặc** `debit` / `credit`."""

    model_config = ConfigDict(extra="forbid")

    date: ColumnName | None = None
    description: ColumnName | None = None
    amount: ColumnName | None = Field(
        default=None, description="Một cột số tiền có dấu: âm = chi, dương = thu"
    )
    debit: ColumnName | None = Field(default=None, description="Cột ghi nợ / tiền ra (chi)")
    credit: ColumnName | None = Field(default=None, description="Cột ghi có / tiền vào (thu)")


class ImportFileInfo(BaseModel):
    file_type: Literal["csv", "xlsx"]
    size_bytes: int
    encoding: str | None = Field(description="Bảng mã CSV đoán được (utf-8, utf-8-sig, cp1258)")
    separator: str | None = Field(description="Dấu phân cách CSV đoán được: `,` `;` hoặc tab")
    separator_label: str | None
    sheet_name: str | None = Field(description="Sheet đã đọc (XLSX)")
    header_row: int = Field(description="Số thứ tự dòng tiêu đề cột trong file (từ 1)")
    headers: list[str]
    warnings: list[str] = []


class ImportMappingInfo(BaseModel):
    column_mapping: ColumnMapping
    date_format: DateFormat
    decimal_style: DecimalStyle
    source: MappingSource = Field(
        description="`guess` = tự đoán, `profile` = mapping đã lưu cho ngân hàng / bộ cột này, "
        "`user` = user vừa chỉnh"
    )
    profile_id: uuid.UUID | None = None
    problems: list[str] = Field(description="Thiếu cột bắt buộc… (rỗng = mapping dùng được)")


class ImportPreviewRow(BaseModel):
    row_index: int = Field(description="Số thứ tự dòng trong file / sheet (từ 1)")
    occurred_on: dt.date | None
    amount: int | None = Field(description="Số nguyên đồng, luôn dương")
    direction: Direction | None
    note: str = Field(description="Nội dung giao dịch (đã gọn khoảng trắng)")
    raw: dict[str, str] = Field(description="Giá trị thô của các cột đã map")
    dedup_hash: str | None
    status: ImportRowStatus
    error: str | None = None
    duplicate_of_row: int | None = Field(
        default=None, description="Dòng trước đó trong cùng file có cùng dedup_hash"
    )
    duplicate_existing: bool = Field(
        default=False, description="Đã có giao dịch import trước đó với cùng dedup_hash"
    )
    transfer_hint: bool = Field(
        default=False,
        description="Có vẻ là chuyển khoản nội bộ / trả nợ thẻ / gửi tiết kiệm (không phải "
        "thu chi thật) — UI mặc định bỏ chọn",
    )
    possible_duplicate_transaction_id: uuid.UUID | None = Field(
        default=None,
        description="Giao dịch nhập tay / từ nguồn khác cùng ngày, số tiền, chiều — có thể trùng",
    )
    warnings: list[str] = []
    suggested_category_id: uuid.UUID | None = None
    suggested_spending_type: SpendingType | None = None
    confidence: float | None = None
    reason: str | None = None
    matched_preference_id: uuid.UUID | None = None
    suggestion_source: SuggestionSource | None = None


class ImportSummary(BaseModel):
    row_count: int
    valid_count: int
    duplicate_count: int
    bad_count: int
    transfer_hint_count: int
    possible_duplicate_count: int
    preference_count: int = Field(description="Dòng phân loại theo sở thích đã học (không gọi AI)")
    ai_count: int = Field(description="Dòng phân loại bởi AI")
    fallback_count: int = Field(description="Dòng chưa phân loại được (tạm Khác, confidence 0)")


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    bank_name: str | None
    file_hash: str
    status: ImportBatchStatus
    row_count: int
    valid_count: int
    duplicate_count: int
    bad_count: int
    committed_count: int
    model: str | None
    ai_error_code: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    committed_at: dt.datetime | None


class ImportPreviewResponse(BaseModel):
    batch: ImportBatchRead
    file_info: ImportFileInfo
    mapping: ImportMappingInfo
    rows: list[ImportPreviewRow]
    summary: ImportSummary
    warnings: list[str]


class ImportMappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_mapping: ColumnMapping
    date_format: DateFormat | None = None
    decimal_style: DecimalStyle | None = None


class ImportCommitRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_index: int
    category_id: uuid.UUID
    spending_type: SpendingType | None = Field(
        default=None, description="Chỉ cho khoản chi; bỏ trống = loại mặc định của danh mục"
    )
    selected: bool = True
    note: Note | None = Field(default=None, description="Bỏ trống = giữ nội dung sao kê")


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ImportCommitRow] = Field(min_length=1, max_length=MAX_COMMIT_ROWS)
    save_mapping_profile: bool = Field(
        default=True, description="Lưu mapping cột cho ngân hàng / bộ tiêu đề cột này"
    )

    @field_validator("rows")
    @classmethod
    def _unique_rows(cls, rows: list[ImportCommitRow]) -> list[ImportCommitRow]:
        seen: set[int] = set()
        for row in rows:
            if row.row_index in seen:
                raise ValueError(f"row_index {row.row_index} bị lặp")
            seen.add(row.row_index)
        return rows


class ImportCommitResult(BaseModel):
    created_count: int
    skipped_duplicate_count: int = Field(
        description="Dòng trùng (trong file / đã import trước đó) — không tạo giao dịch"
    )
    bad_count: int = Field(description="Dòng lỗi của file — không tạo giao dịch")
    not_selected_count: int = Field(description="Dòng hợp lệ user bỏ chọn")
    batch: ImportBatchRead


class ImportMappingProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_name: str
    headers_hash: str
    headers: list[str] | None
    column_mapping: ColumnMapping
    date_format: DateFormat | None
    decimal_style: DecimalStyle | None
    last_used_at: dt.datetime | None


class ImportMappingProfileList(BaseModel):
    items: list[ImportMappingProfileRead]


class ImportConflictResponse(BaseModel):
    """409: `IMPORT_ALREADY_COMMITTED` kèm id lô đã import (để mở danh sách giao dịch)."""

    detail: str
    code: str
    import_batch_id: uuid.UUID | None = None


# ---------- giao tiếp với tầng AI (router truyền closure vào service) ----------


class ImportClassifyItem(BaseModel):
    """Một dòng cần phân loại — chỉ gồm nội dung đã che số dài, số tiền, chiều, ngày."""

    row_index: int
    note: str
    amount: int
    direction: Direction
    occurred_on: dt.date


class ImportClassification(BaseModel):
    """Kết quả phân loại hàng loạt (không raise lỗi AI)."""

    suggestions: dict[int, ClassificationSuggestion] = {}
    sources: dict[int, SuggestionSource] = {}
    model: str | None = None
    llm_requests: int = 0
    error_code: str | None = None
    error_message: str | None = None


class ImportClassificationItemOutput(BaseModel):
    row_index: int = Field(description="row_index của dòng được gửi")
    category_slug: str = Field(description="Slug thuộc danh sách danh mục, cùng loại với direction")
    spending_type: SpendingType | None = Field(description="Bắt buộc với expense; null với income")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=200, description="Lý do ngắn, tiếng Việt, trung lập")


class ImportClassificationOutput(BaseModel):
    """Structured output của model cho một nhóm ≤ 20 dòng sao kê."""

    items: list[ImportClassificationItemOutput]


__all__ = [
    "BankName",
    "ColumnMapping",
    "DateFormat",
    "DecimalStyle",
    "ImportBatchRead",
    "ImportClassification",
    "ImportClassificationItemOutput",
    "ImportClassificationOutput",
    "ImportClassifyItem",
    "ImportCommitRequest",
    "ImportCommitResult",
    "ImportCommitRow",
    "ImportConflictResponse",
    "ImportFileInfo",
    "ImportMappingInfo",
    "ImportMappingProfileList",
    "ImportMappingProfileRead",
    "ImportMappingUpdate",
    "ImportPreviewResponse",
    "ImportPreviewRow",
    "ImportSummary",
]
