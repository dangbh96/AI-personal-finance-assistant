import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.ai import receipt_vision
from app.api import embedding_hook
from app.core.db import DbSession
from app.models.enums import ReceiptStatus
from app.schemas.classification import PreferenceRead
from app.schemas.common import ErrorResponse
from app.schemas.receipt import (
    ReceiptConfirm,
    ReceiptConfirmResult,
    ReceiptDetail,
    ReceiptList,
    ReceiptRead,
)
from app.schemas.transaction import TransactionRead
from app.services import goal_service, receipt_service, receipt_storage
from app.services.receipt_service import Analyzer

router = APIRouter(prefix="/receipts", tags=["receipts"])

Today = Annotated[
    date | None,
    Query(description="Ngày hiện tại phía user (draft dùng khi hoá đơn không có ngày)"),
]


def _analyzer(db: Session, today: date) -> Analyzer:
    def analyze(content: bytes, mime_type: str, receipt_id: uuid.UUID):
        return receipt_vision.analyze(db, content, mime_type, receipt_id=receipt_id, today=today)

    return analyze


@router.post(
    "",
    response_model=ReceiptDetail,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"model": ErrorResponse, "description": "Ảnh lớn hơn 10MB"},
        415: {"model": ErrorResponse, "description": "Không phải ảnh JPEG/PNG/WEBP/HEIC/HEIF"},
        422: {"model": ErrorResponse},
    },
)
def upload_receipt(
    db: DbSession,
    file: Annotated[UploadFile, File(description="Ảnh hoá đơn (≤ 10MB)")],
    today: Today = None,
):
    """Upload ảnh hoá đơn và trích xuất ngay bằng AI vision. **Không tạo giao dịch** — trả draft
    (`status = extracted`) hoặc form nhập tay điền sẵn (`status = failed`); user xác nhận qua
    `POST /receipts/{id}/confirm`. Ảnh lưu local trong `UPLOAD_DIR` và được gửi tới OpenAI."""
    today = today or date.today()
    receipt_storage.check_declared_type(
        file.content_type, receipt_storage.clean_filename(file.filename)
    )
    if file.size is not None and file.size > receipt_storage.MAX_RECEIPT_BYTES:
        raise receipt_storage.FileTooLarge()
    content = file.file.read(receipt_storage.MAX_RECEIPT_BYTES + 1)
    return receipt_service.upload_receipt(
        db,
        content=content,
        content_type=file.content_type,
        filename=file.filename,
        analyzer=_analyzer(db, today),
        today=today,
    )


@router.get("", response_model=ReceiptList, responses={422: {"model": ErrorResponse}})
def list_receipts(
    db: DbSession,
    receipt_status: Annotated[ReceiptStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Lịch sử hoá đơn đã upload, mới nhất trước."""
    return ReceiptList(items=receipt_service.list_receipts(db, status=receipt_status, limit=limit))


@router.get(
    "/{receipt_id}", response_model=ReceiptDetail, responses={404: {"model": ErrorResponse}}
)
def get_receipt(db: DbSession, receipt_id: uuid.UUID, today: Today = None):
    return receipt_service.get_receipt_detail(db, receipt_id, today or date.today())


@router.post(
    "/{receipt_id}/retry",
    response_model=ReceiptDetail,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def retry_receipt(db: DbSession, receipt_id: uuid.UUID, today: Today = None):
    """Đọc lại hoá đơn `failed` / `uploaded` (cùng receipt, cùng file). Không tạo giao dịch."""
    today = today or date.today()
    return receipt_service.retry_receipt(db, receipt_id, _analyzer(db, today), today)


@router.post(
    "/{receipt_id}/confirm",
    response_model=ReceiptConfirmResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def confirm_receipt(db: DbSession, receipt_id: uuid.UUID, data: ReceiptConfirm):
    """Tạo giao dịch (`source='receipt'`, `receipt_id`) từ draft user đã kiểm tra / sửa;
    receipt chuyển `confirmed`. Sửa danh mục so với đề xuất AI → học theo tên cửa hàng."""
    transaction, receipt, learned = receipt_service.confirm_receipt(db, receipt_id, data)
    result = ReceiptConfirmResult(
        transaction=TransactionRead.model_validate(transaction),
        receipt=ReceiptRead.model_validate(receipt),
        learned_preference=PreferenceRead.model_validate(learned) if learned else None,
        pyf_proposal=goal_service.proposal_for_new_income(db, transaction, date.today()),
    )
    embedding_hook.index_transactions(db, [transaction.id])
    return result


@router.get(
    "/{receipt_id}/file",
    response_class=Response,
    responses={
        200: {"content": {"image/*": {}}, "description": "Ảnh hoá đơn (HEIC/HEIF → JPEG)"},
        404: {"model": ErrorResponse},
    },
)
def get_receipt_file(db: DbSession, receipt_id: uuid.UUID) -> Response:
    content, media_type = receipt_service.receipt_image(db, receipt_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
