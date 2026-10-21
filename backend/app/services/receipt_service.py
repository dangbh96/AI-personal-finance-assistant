"""Nghiệp vụ hoá đơn (Phase 13) — deterministic, không gọi AI trực tiếp (ADR-005).

Luồng upload: validate + lưu file (`receipt_storage`) → receipt `uploaded` (commit) → `analyzer`
(tầng AI do router truyền vào, vì `services` không import `ai`) → map extraction thành draft
(`receipt_mapping`) → `extracted`, hoặc `failed` + form nhập tay điền sẵn. Không tạo giao dịch:
giao dịch chỉ được tạo ở `confirm_receipt` khi user xác nhận (receipt → `confirmed`).
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import Category, ClassificationPreference, Receipt, Transaction
from app.repositories import category_repository, receipt_repository, transaction_repository
from app.schemas.ai import ClassificationSuggestion, TransactionDraft
from app.schemas.receipt import (
    ReceiptAnalysis,
    ReceiptConfirm,
    ReceiptDetail,
    ReceiptListItem,
    ReceiptRead,
    ReceiptVisionOutput,
)
from app.schemas.transaction import TransactionRead
from app.services import classification_preference_service, receipt_storage, transaction_service
from app.services.receipt_mapping import (
    assess_extraction,
    build_draft,
    build_manual_prefill,
    extraction_warnings,
    merchant_pattern,
)

logger = logging.getLogger(__name__)

# (ảnh đã chuẩn hoá cho model, mime, receipt id) → kết quả trích xuất; không raise lỗi AI.
Analyzer = Callable[[bytes, str, uuid.UUID], ReceiptAnalysis]

FALLBACK_CATEGORY_SLUG = "other"
RETRYABLE_STATUSES = frozenset({"uploaded", "failed"})
SUGGESTION_KEY = "suggestion"
MAX_RAW_INPUT = 2000


def get_receipt(db: Session, receipt_id: uuid.UUID) -> Receipt:
    receipt = receipt_repository.get(db, receipt_id)
    if receipt is None:
        raise NotFoundError("Không tìm thấy hoá đơn", "receipt_not_found")
    return receipt


# ---------- đọc extraction đã lưu ----------


def stored_extraction(receipt: Receipt) -> ReceiptVisionOutput | None:
    if not isinstance(receipt.extracted, dict):
        return None
    try:
        return ReceiptVisionOutput.model_validate(receipt.extracted)
    except ValidationError:
        return None


def stored_suggestion(receipt: Receipt) -> ClassificationSuggestion | None:
    raw = receipt.extracted.get(SUGGESTION_KEY) if isinstance(receipt.extracted, dict) else None
    if not isinstance(raw, dict):
        return None
    try:
        return ClassificationSuggestion.model_validate(raw)
    except ValidationError:
        return None


def stored_draft(receipt: Receipt) -> TransactionDraft | None:
    if not isinstance(receipt.draft, dict):
        return None
    try:
        return TransactionDraft.model_validate(receipt.draft)
    except ValidationError:
        return None


def _usable_category(db: Session, slug: str | None) -> Category | None:
    """Danh mục chi đang dùng theo slug đề xuất; không có → `other`."""
    for candidate in (slug, FALLBACK_CATEGORY_SLUG):
        if not candidate:
            continue
        category = category_repository.get_by_slug(db, candidate)
        if category is not None and category.kind == "expense" and not category.is_archived:
            return category
    return None


# ---------- upload / trích xuất ----------


def _apply_analysis(db: Session, receipt: Receipt, analysis: ReceiptAnalysis, today: date) -> None:
    receipt.model = analysis.model
    receipt.draft = None
    if analysis.output is None:
        receipt.extracted = None
        receipt.status = "failed"
        receipt.error_code = analysis.error_code or "AI_UNAVAILABLE"
        receipt.error_message = analysis.error_message or "Không đọc được hoá đơn."
        return

    output = analysis.output
    suggestion = analysis.suggestion or ClassificationSuggestion(
        category_slug=output.category_slug,
        spending_type=output.spending_type,
        confidence=output.confidence,
        reason=output.classification_reason,
    )
    receipt.extracted = {
        **output.model_dump(mode="json"),
        SUGGESTION_KEY: suggestion.model_dump(mode="json"),
    }
    assessment = assess_extraction(output)
    category = _usable_category(db, suggestion.category_slug)
    if assessment.usable and category is not None:
        draft = build_draft(output, category, suggestion, today)
        receipt.draft = draft.model_dump(mode="json")
        receipt.status = "extracted"
        receipt.error_code = None
        receipt.error_message = None
    elif not assessment.usable:
        receipt.status = "failed"
        receipt.error_code = assessment.error_code
        receipt.error_message = assessment.error_message
    else:
        receipt.status = "failed"
        receipt.error_code = "category_missing"
        receipt.error_message = "Không có danh mục chi tiêu nào đang dùng để gợi ý."


def _run_extraction(
    db: Session, receipt: Receipt, analyzer: Analyzer, today: date
) -> ReceiptDetail:
    content = receipt_storage.read_file(receipt.file_path)
    if content is None:
        analysis = ReceiptAnalysis(
            error_code="file_missing", error_message="Không tìm thấy file ảnh của hoá đơn này."
        )
    else:
        try:
            payload, mime_type = receipt_storage.vision_payload(content, receipt.mime_type)
        except DomainError as exc:
            analysis = ReceiptAnalysis(error_code=exc.code, error_message=exc.detail)
        else:
            analysis = analyzer(payload, mime_type, receipt.id)
    _apply_analysis(db, receipt, analysis, today)
    db.commit()
    db.refresh(receipt)
    logger.info(
        "receipt id=%s status=%s error_code=%s model=%s",
        receipt.id,
        receipt.status,
        receipt.error_code,
        receipt.model,
    )
    return build_detail(db, receipt, today)


def upload_receipt(
    db: Session,
    *,
    content: bytes,
    content_type: str | None,
    filename: str | None,
    analyzer: Analyzer,
    today: date,
) -> ReceiptDetail:
    """Validate + lưu ảnh, tạo receipt `uploaded` rồi trích xuất ngay. Không tạo giao dịch."""
    image = receipt_storage.validate_image(content, content_type, filename)
    receipt_id = uuid.uuid4()
    now = datetime.now(UTC)
    relative = receipt_storage.relative_path(receipt_id, now.date(), image.extension)
    receipt_storage.save_file(relative, image.content)
    receipt = Receipt(
        id=receipt_id,
        file_path=relative,
        mime_type=image.mime_type,
        original_filename=image.original_filename,
        file_size_bytes=image.size,
        sha256=image.sha256,
        status="uploaded",
        created_at=now,
        updated_at=now,
    )
    try:
        receipt_repository.add(db, receipt)
        db.commit()
    except Exception:
        db.rollback()
        receipt_storage.delete_file(relative)
        raise
    logger.info("receipt id=%s uploaded mime=%s size=%d", receipt.id, receipt.mime_type, image.size)
    return _run_extraction(db, receipt, analyzer, today)


def retry_receipt(
    db: Session, receipt_id: uuid.UUID, analyzer: Analyzer, today: date
) -> ReceiptDetail:
    """Trích xuất lại receipt `failed` / `uploaded` (cùng id, cùng file)."""
    receipt = get_receipt(db, receipt_id)
    if receipt.status not in RETRYABLE_STATUSES:
        raise ConflictError(
            "Chỉ đọc lại được hoá đơn chưa đọc được hoặc đang chờ đọc", "receipt_not_retryable"
        )
    return _run_extraction(db, receipt, analyzer, today)


# ---------- đọc ----------


def build_detail(db: Session, receipt: Receipt, today: date) -> ReceiptDetail:
    extraction = stored_extraction(receipt)
    draft = stored_draft(receipt)
    prefill = None
    if receipt.status in RETRYABLE_STATUSES:
        suggestion = stored_suggestion(receipt)
        category = (
            _usable_category(db, suggestion.category_slug if suggestion else None)
            if extraction is not None
            else None
        )
        prefill = build_manual_prefill(extraction, category, suggestion, today)
    duplicate = receipt_repository.latest_other_with_sha256(db, receipt.sha256, receipt.id)
    warnings = extraction_warnings(extraction, today) if extraction is not None else []
    if duplicate is not None:
        warnings.insert(
            0,
            "Ảnh này đã được tải lên trước đó"
            + (" và đã lưu thành giao dịch" if duplicate.status == "confirmed" else "")
            + " — bạn kiểm tra để tránh ghi trùng nhé.",
        )
    transaction = (
        transaction_repository.get(db, receipt.transaction_id) if receipt.transaction_id else None
    )
    return ReceiptDetail(
        receipt=ReceiptRead.model_validate(receipt),
        status=receipt.status,  # type: ignore[arg-type]
        extraction=extraction,
        transaction_draft=draft,
        manual_prefill=prefill,
        warnings=warnings,
        duplicate_of=duplicate.id if duplicate is not None else None,
        transaction=TransactionRead.model_validate(transaction) if transaction else None,
    )


def get_receipt_detail(db: Session, receipt_id: uuid.UUID, today: date) -> ReceiptDetail:
    return build_detail(db, get_receipt(db, receipt_id), today)


def list_receipts(db: Session, *, status: str | None, limit: int) -> list[ReceiptListItem]:
    receipts = receipt_repository.list_receipts(db, status=status, limit=limit)
    tx_dates = {
        t.id: t.occurred_on
        for t in transaction_repository.get_many(
            db, [r.transaction_id for r in receipts if r.transaction_id]
        )
    }
    items = []
    for receipt in receipts:
        extraction = stored_extraction(receipt)
        items.append(
            ReceiptListItem(
                id=receipt.id,
                status=receipt.status,  # type: ignore[arg-type]
                original_filename=receipt.original_filename,
                merchant=extraction.merchant if extraction else None,
                total=extraction.total if extraction else None,
                receipt_date=extraction.date if extraction else None,
                error_code=receipt.error_code,
                transaction_id=receipt.transaction_id,
                transaction_occurred_on=tx_dates.get(receipt.transaction_id)
                if receipt.transaction_id
                else None,
                created_at=receipt.created_at,
            )
        )
    return items


def receipt_image(db: Session, receipt_id: uuid.UUID) -> tuple[bytes, str]:
    """Ảnh để xem trước: HEIC/HEIF đổi sang JPEG (trình duyệt đa phần không hiển thị được)."""
    receipt = get_receipt(db, receipt_id)
    content = receipt_storage.read_file(receipt.file_path)
    if content is None:
        raise NotFoundError("Không tìm thấy file ảnh của hoá đơn này", "receipt_file_missing")
    if receipt.mime_type in receipt_storage.CONVERT_TO_JPEG:
        return receipt_storage.to_jpeg(content), "image/jpeg"
    return content, receipt.mime_type


# ---------- xác nhận ----------


def _ai_suggestion(receipt: Receipt) -> dict[str, Any] | None:
    """Draft gốc (chưa sửa) + extraction — lưu vào `transactions.ai_suggestion`."""
    extraction = stored_extraction(receipt)
    if extraction is None and receipt.draft is None:
        return None
    payload: dict[str, Any] = dict(receipt.draft) if isinstance(receipt.draft, dict) else {}
    payload["model"] = receipt.model
    payload["receipt_extraction"] = extraction.model_dump(mode="json") if extraction else None
    return payload


def _raw_input(receipt: Receipt, extraction: ReceiptVisionOutput | None) -> str:
    merchant = extraction.merchant.strip() if extraction and extraction.merchant else None
    label = f"Hoá đơn {merchant}" if merchant else "Hoá đơn"
    return f"{label} ({receipt.original_filename})"[:MAX_RAW_INPUT]


def confirm_receipt(
    db: Session, receipt_id: uuid.UUID, data: ReceiptConfirm
) -> tuple[Transaction, Receipt, ClassificationPreference | None]:
    """Tạo giao dịch `source='receipt'` từ giá trị user đã kiểm tra; receipt → `confirmed`.

    Học phân loại (Phase 3) chỉ khi có draft AI: user sửa danh mục / loại chi tiêu → học theo tên
    cửa hàng (không đoán từ khoá từ ghi chú). 1 commit.
    """
    receipt = get_receipt(db, receipt_id)
    if receipt.status == "confirmed":
        raise ConflictError("Hoá đơn này đã được lưu thành giao dịch", "receipt_already_confirmed")
    category = transaction_service.resolve_category(db, data.category_id, data.direction)
    extraction = stored_extraction(receipt)
    transaction = Transaction(
        direction=data.direction,
        amount=data.amount,
        occurred_on=data.occurred_on,
        note=data.note,
        category=category,
        spending_type=transaction_service.resolve_spending_type(
            data.direction, data.spending_type, category
        ),
        source="receipt",
        raw_input=_raw_input(receipt, extraction),
        ai_suggestion=_ai_suggestion(receipt),
        receipt_id=receipt.id,
    )
    transaction_repository.add(db, transaction)
    learned = None
    if receipt.draft is not None:
        learned = classification_preference_service.record_feedback(
            db,
            transaction,
            keyword=merchant_pattern(extraction.merchant if extraction else None),
            guess_keyword=False,
        )
    receipt.status = "confirmed"
    receipt.transaction_id = transaction.id
    receipt.error_code = None
    receipt.error_message = None
    db.commit()
    db.refresh(transaction)
    db.refresh(receipt)
    if learned is not None:
        db.refresh(learned)
    logger.info("receipt id=%s confirmed transaction=%s", receipt.id, transaction.id)
    return transaction, receipt, learned
