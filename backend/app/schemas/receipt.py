"""Schema Receipt OCR (Phase 13).

`ReceiptExtraction` là phần trích xuất theo plan; `ReceiptVisionOutput` = extraction + đề xuất phân
loại (model vision chọn danh mục chi trong cùng lời gọi). Endpoint upload / retry chỉ trả draft —
giao dịch chỉ được tạo khi user gọi `POST /receipts/{id}/confirm`.
"""

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Direction, ReceiptStatus, SpendingType
from app.schemas.ai import ClassificationSuggestion, TransactionDraft
from app.schemas.classification import PreferenceRead
from app.schemas.goal import PyfProposal
from app.schemas.transaction import Amount, Note, TransactionRead

MAX_RECEIPT_ITEMS = 60


class ReceiptItem(BaseModel):
    name: str = Field(max_length=200, description="Tên dòng hàng đúng như in trên hoá đơn")
    qty: float | None = Field(description="Số lượng nếu thấy rõ, không thì null")
    amount: int | None = Field(
        description="Thành tiền của dòng (số nguyên đồng); null nếu không đọc rõ"
    )


class ReceiptExtraction(BaseModel):
    """Dữ liệu đọc được trên ảnh hoá đơn (không đoán khi không chắc)."""

    merchant: str | None = Field(max_length=200, description="Tên cửa hàng / nơi bán")
    date: dt.date | None = Field(description="Ngày trên hoá đơn (YYYY-MM-DD), null nếu không rõ")
    total: int | None = Field(
        description="Tổng khách phải thanh toán, số nguyên đồng; null nếu không đọc rõ"
    )
    currency: str = Field(max_length=10, description="Mã tiền tệ, mặc định VND")
    items: list[ReceiptItem] = Field(max_length=MAX_RECEIPT_ITEMS)
    confidence: float = Field(ge=0, le=1, description="Độ tin cậy tổng thể của phần đọc được")
    unreadable_reason: str | None = Field(
        max_length=300,
        description="Lý do không đọc được (mờ, không phải hoá đơn…), null nếu đọc được",
    )


class ReceiptVisionOutput(ReceiptExtraction):
    """Structured output của model vision: extraction + đề xuất danh mục chi tiêu."""

    category_slug: str = Field(description="Slug danh mục chi tiêu thuộc danh sách gửi kèm")
    spending_type: SpendingType = Field(description="Loại chi tiêu đề xuất")
    classification_reason: str = Field(max_length=300, description="Vì sao chọn danh mục")


class ReceiptAnalysis(BaseModel):
    """Kết quả một lần trích xuất do tầng AI trả cho `receipt_service` (không raise lỗi AI).

    Lỗi AI (chưa cấu hình, timeout, output sai…) → `error_code` / `error_message`, không có output.
    """

    output: ReceiptVisionOutput | None = None
    suggestion: ClassificationSuggestion | None = None
    model: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReceiptManualPrefill(BaseModel):
    """Giá trị điền sẵn cho form nhập tay khi trích xuất thất bại / chưa đủ tin cậy."""

    direction: Direction = "expense"
    amount: int | None
    occurred_on: dt.date
    note: str
    category_id: uuid.UUID | None
    category_slug: str | None
    spending_type: SpendingType | None


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ReceiptStatus
    mime_type: str
    original_filename: str
    file_size_bytes: int
    sha256: str
    model: str | None
    error_code: str | None
    error_message: str | None
    transaction_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class ReceiptDetail(BaseModel):
    """Response upload / retry / chi tiết: trạng thái + extraction + draft (hoặc form nhập tay)."""

    receipt: ReceiptRead
    status: ReceiptStatus
    extraction: ReceiptVisionOutput | None = Field(
        description="Output model vision (kể cả khi chưa đủ tin cậy); null nếu AI lỗi"
    )
    transaction_draft: TransactionDraft | None = Field(
        description="Draft đầy đủ khi `status = extracted`; chưa lưu DB"
    )
    manual_prefill: ReceiptManualPrefill | None = Field(
        description="Khi `status = failed` (hoặc `uploaded`): điền sẵn phần đoán được"
    )
    warnings: list[str] = Field(description="Cảnh báo deterministic (ngày, tổng dòng hàng…)")
    duplicate_of: uuid.UUID | None = Field(
        description="Receipt khác có cùng nội dung ảnh (sha256) đã upload trước đó"
    )
    transaction: TransactionRead | None = Field(
        description="Giao dịch đã tạo khi `status = confirmed` (null nếu đã bị xoá)"
    )


class ReceiptListItem(BaseModel):
    id: uuid.UUID
    status: ReceiptStatus
    original_filename: str
    merchant: str | None
    total: int | None
    receipt_date: dt.date | None
    error_code: str | None
    transaction_id: uuid.UUID | None
    transaction_occurred_on: dt.date | None = Field(
        description="Ngày của giao dịch đã lưu (để link sang /transactions đúng tháng)"
    )
    created_at: dt.datetime


class ReceiptList(BaseModel):
    items: list[ReceiptListItem]


class ReceiptConfirm(BaseModel):
    """Giá trị user đã kiểm tra / sửa từ draft (hoặc form nhập tay). `source`, `raw_input`,
    `ai_suggestion`, `receipt_id` do backend đặt."""

    model_config = ConfigDict(extra="forbid")

    direction: Direction = "expense"
    amount: Amount
    occurred_on: dt.date
    category_id: uuid.UUID
    spending_type: SpendingType | None = Field(
        default=None,
        description="Chỉ cho expense; bỏ trống thì dùng default_spending_type của category",
    )
    note: Note | None = None

    @field_validator("note", mode="before")
    @classmethod
    def _blank_note(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ReceiptConfirmResult(BaseModel):
    transaction: TransactionRead
    receipt: ReceiptRead
    learned_preference: PreferenceRead | None = None
    pyf_proposal: PyfProposal | None = None
