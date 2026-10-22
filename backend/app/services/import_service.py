"""Nghiệp vụ import sao kê CSV / Excel (Phase 14) — deterministic, không gọi AI trực tiếp.

Luồng: `preview_import` (đọc file → đoán mapping / dùng profile đã lưu → chuẩn hoá + dedup →
`classifier` do router truyền vào (tầng AI, vì `services` không import `ai`) → lưu batch
`previewed` + các dòng preview, **không tạo giao dịch**) → user sửa mapping (`update_mapping`) /
danh mục / chọn dòng → `commit_import` tạo giao dịch `source='import'` trong **một** DB
transaction (lỗi → rollback toàn bộ), bỏ qua dòng trùng / lỗi, lưu mapping profile.
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import (
    Category,
    ClassificationFeedback,
    ImportBatch,
    ImportMappingProfile,
    Transaction,
)
from app.repositories import (
    category_repository,
    classification_feedback_repository,
    import_batch_repository,
    transaction_repository,
)
from app.schemas.ai import DEFAULT_TIMEZONE, ClassificationSuggestion
from app.schemas.imports import (
    ColumnMapping,
    DateFormat,
    DecimalStyle,
    ImportBatchRead,
    ImportClassification,
    ImportClassifyItem,
    ImportCommitRequest,
    ImportCommitResult,
    ImportFileInfo,
    ImportMappingInfo,
    ImportMappingUpdate,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportSummary,
    MappingSource,
)
from app.services import classification_preference_service, import_parsing, transaction_service
from app.services.import_reader import SEPARATOR_LABELS, clean_filename, read_table

logger = logging.getLogger(__name__)

# Danh sách dòng cần phân loại → đề xuất theo row_index (tầng AI; không raise lỗi AI).
Classifier = Callable[[list[ImportClassifyItem]], ImportClassification]

FALLBACK_SLUGS = {"expense": "other", "income": "other_income"}
FALLBACK_REASON = "Chưa phân loại được — bạn chọn danh mục giúp nhé."
MAX_RAW_INPUT = 2000
EDITABLE_STATUSES = frozenset({"previewed", "failed"})


class ImportAlreadyCommitted(ConflictError):
    def __init__(self, batch: ImportBatch) -> None:
        moment = (batch.committed_at or batch.updated_at).astimezone(ZoneInfo(DEFAULT_TIMEZONE))
        when = moment.strftime("%d/%m/%Y")
        super().__init__(
            f"File “{batch.filename}” đã được import ngày {when} ({batch.committed_count} giao "
            "dịch) — không import lại để tránh ghi trùng.",
            "IMPORT_ALREADY_COMMITTED",
        )
        self.extra = {"import_batch_id": str(batch.id)}


# ---------- đọc batch ----------


def get_batch(db: Session, batch_id: uuid.UUID) -> ImportBatch:
    batch = import_batch_repository.get(db, batch_id)
    if batch is None:
        raise NotFoundError("Không tìm thấy lô import", "import_batch_not_found")
    return batch


def stored_rows(batch: ImportBatch) -> list[ImportPreviewRow]:
    rows = []
    for raw in batch.rows or []:
        try:
            rows.append(ImportPreviewRow.model_validate(raw))
        except ValidationError:
            continue
    return rows


def _file_info(batch: ImportBatch) -> ImportFileInfo:
    return ImportFileInfo.model_validate(batch.file_info or {})


def _stored_mapping(batch: ImportBatch) -> ColumnMapping:
    try:
        return ColumnMapping.model_validate(batch.column_mapping or {})
    except ValidationError:
        return ColumnMapping()


def summarize(rows: Iterable[ImportPreviewRow]) -> ImportSummary:
    rows = list(rows)
    valid = [r for r in rows if r.status == "valid"]
    return ImportSummary(
        row_count=len(rows),
        valid_count=len(valid),
        duplicate_count=sum(1 for r in rows if r.status == "duplicate"),
        bad_count=sum(1 for r in rows if r.status == "bad"),
        transfer_hint_count=sum(1 for r in valid if r.transfer_hint),
        possible_duplicate_count=sum(1 for r in valid if r.possible_duplicate_transaction_id),
        preference_count=sum(1 for r in valid if r.suggestion_source == "preference"),
        ai_count=sum(1 for r in valid if r.suggestion_source == "ai"),
        fallback_count=sum(1 for r in valid if r.suggestion_source == "fallback"),
    )


def _preview_warnings(batch: ImportBatch, summary: ImportSummary) -> list[str]:
    warnings = []
    if batch.ai_error_code and summary.fallback_count:
        warnings.append(
            f"AI chưa phân loại được {summary.fallback_count} dòng ({batch.ai_error_code}) — các "
            "dòng này tạm để “Khác”, bạn chọn lại danh mục giúp nhé."
        )
    if summary.transfer_hint_count:
        warnings.append(
            f"{summary.transfer_hint_count} dòng có vẻ là chuyển khoản nội bộ / trả nợ thẻ / gửi "
            "tiết kiệm — không phải thu chi thật nên đang được bỏ chọn; bạn chọn lại nếu muốn "
            "ghi nhận."
        )
    if summary.possible_duplicate_count:
        warnings.append(
            f"{summary.possible_duplicate_count} dòng trùng ngày, số tiền với giao dịch bạn đã "
            "nhập trước đó — kiểm tra để tránh ghi hai lần nhé."
        )
    return warnings


def build_preview(batch: ImportBatch) -> ImportPreviewResponse:
    rows = stored_rows(batch)
    summary = summarize(rows)
    file_info = _file_info(batch)
    mapping = _stored_mapping(batch)
    return ImportPreviewResponse(
        batch=ImportBatchRead.model_validate(batch),
        file_info=file_info,
        mapping=ImportMappingInfo(
            column_mapping=mapping,
            date_format=batch.date_format or import_parsing.DEFAULT_DATE_FORMAT,  # type: ignore[arg-type]
            decimal_style=batch.decimal_style or import_parsing.DEFAULT_DECIMAL_STYLE,  # type: ignore[arg-type]
            source=batch.mapping_source or "guess",  # type: ignore[arg-type]
            profile_id=(batch.file_info or {}).get("profile_id"),
            problems=import_parsing.mapping_problems(mapping, file_info.headers),
        ),
        rows=rows,
        summary=summary,
        warnings=_preview_warnings(batch, summary),
    )


def get_preview(db: Session, batch_id: uuid.UUID) -> ImportPreviewResponse:
    return build_preview(get_batch(db, batch_id))


# ---------- phân loại ----------


def _active_categories(db: Session) -> dict[str, Category]:
    return {c.slug: c for c in category_repository.list_categories(db)}


def _resolve_suggestion(
    suggestion: ClassificationSuggestion | None, direction: str, categories: dict[str, Category]
) -> tuple[Category | None, str | None, ClassificationSuggestion | None]:
    """Danh mục đang dùng, cùng chiều tiền với dòng; không có → `other` / `other_income`."""
    category = categories.get(suggestion.category_slug) if suggestion else None
    if category is None or category.kind != direction:
        category = categories.get(FALLBACK_SLUGS[direction])
        suggestion = None
    if category is None:
        return None, None, None
    if direction == "income":
        spending_type = None
    else:
        spending_type = (
            suggestion.spending_type if suggestion and suggestion.spending_type else None
        ) or category.default_spending_type
    return category, spending_type, suggestion


def _classify(
    rows: list[ImportPreviewRow],
    classifier: Classifier,
    categories: dict[str, Category],
    cache: dict[tuple[str, str], ImportPreviewRow],
) -> tuple[list[ImportPreviewRow], ImportClassification | None]:
    """Gắn đề xuất phân loại cho dòng hợp lệ. `cache`: đề xuất cũ theo (nội dung, chiều) khi user
    đổi mapping — không gọi lại AI cho dòng đã phân loại."""
    pending: list[ImportClassifyItem] = []
    for row in rows:
        if row.status != "valid" or (row.note.lower(), row.direction) in cache:
            continue
        pending.append(
            ImportClassifyItem(
                row_index=row.row_index,
                note=import_parsing.prompt_safe_description(row.note),
                amount=row.amount,  # type: ignore[arg-type]
                direction=row.direction,  # type: ignore[arg-type]
                occurred_on=row.occurred_on,  # type: ignore[arg-type]
            )
        )
    classification = classifier(pending) if pending else None

    result = []
    for row in rows:
        if row.status != "valid":
            result.append(row)
            continue
        cached = cache.get((row.note.lower(), row.direction or ""))
        if cached is not None and cached.suggested_category_id is not None:
            result.append(
                row.model_copy(
                    update={
                        key: getattr(cached, key)
                        for key in (
                            "suggested_category_id",
                            "suggested_spending_type",
                            "confidence",
                            "reason",
                            "matched_preference_id",
                            "suggestion_source",
                        )
                    }
                )
            )
            continue
        suggestion = classification.suggestions.get(row.row_index) if classification else None
        source = (
            classification.sources.get(row.row_index, "ai")
            if classification and suggestion
            else None
        )
        category, spending_type, used = _resolve_suggestion(
            suggestion, row.direction or "expense", categories
        )
        result.append(
            row.model_copy(
                update={
                    "suggested_category_id": category.id if category else None,
                    "suggested_spending_type": spending_type,
                    "confidence": used.confidence if used else 0.0,
                    "reason": used.reason if used else FALLBACK_REASON,
                    "matched_preference_id": used.matched_preference_id if used else None,
                    "suggestion_source": source if used else "fallback",
                }
            )
        )
    return result, classification


# ---------- dựng preview ----------


def _parse(
    db: Session,
    table_rows: list[list[str]],
    header_index: int,
    headers: list[str],
    mapping: ColumnMapping,
    date_format: DateFormat,
    decimal_style: DecimalStyle,
) -> list[ImportPreviewRow]:
    args = (table_rows, header_index, headers, mapping, date_format, decimal_style)
    parsed = import_parsing.parse_rows(*args)
    hashes = {r.dedup_hash for r in parsed if r.dedup_hash}
    existing = transaction_repository.existing_dedup_hashes(db, hashes)
    if existing:
        parsed = import_parsing.parse_rows(*args, existing_hashes=existing)

    valid_dates = [r.occurred_on for r in parsed if r.status == "valid" and r.occurred_on]
    manual = (
        transaction_repository.non_import_keys_between(db, min(valid_dates), max(valid_dates))
        if valid_dates
        else {}
    )
    rows = []
    for item in parsed:
        warnings = list(item.warnings)
        possible = None
        if item.status == "valid":
            possible = manual.get((item.occurred_on, item.amount, item.direction))  # type: ignore[arg-type]
            if possible is not None:
                warnings.append("Có giao dịch đã nhập cùng ngày, cùng số tiền — có thể trùng.")
            if item.transfer_hint:
                warnings.append(
                    "Có vẻ là chuyển khoản nội bộ / trả nợ thẻ / gửi tiết kiệm — không phải thu "
                    "chi thật."
                )
        rows.append(
            ImportPreviewRow(
                row_index=item.row_index,
                occurred_on=item.occurred_on,
                amount=item.amount,
                direction=item.direction,  # type: ignore[arg-type]
                note=item.note,
                raw=item.raw,
                dedup_hash=item.dedup_hash,
                status=item.status,  # type: ignore[arg-type]
                error=item.error,
                duplicate_of_row=item.duplicate_of_row,
                duplicate_existing=item.duplicate_existing,
                transfer_hint=item.transfer_hint,
                possible_duplicate_transaction_id=possible,
                warnings=warnings,
            )
        )
    return rows


def _apply_preview(
    db: Session,
    batch: ImportBatch,
    *,
    mapping: ColumnMapping,
    date_format: DateFormat,
    decimal_style: DecimalStyle,
    mapping_source: MappingSource,
    classifier: Classifier,
    cache: dict[tuple[str, str], ImportPreviewRow] | None = None,
) -> None:
    info = _file_info(batch)
    header_index = info.header_row - 1
    rows = _parse(
        db, batch.source_rows or [], header_index, info.headers, mapping, date_format, decimal_style
    )
    rows, classification = _classify(rows, classifier, _active_categories(db), cache or {})
    summary = summarize(rows)
    batch.column_mapping = mapping.model_dump(exclude_none=True)
    batch.date_format = date_format
    batch.decimal_style = decimal_style
    batch.mapping_source = mapping_source
    batch.rows = [r.model_dump(mode="json") for r in rows]
    batch.row_count = summary.row_count
    batch.valid_count = summary.valid_count
    batch.duplicate_count = summary.duplicate_count
    batch.bad_count = summary.bad_count
    if classification is not None:
        batch.model = classification.model or batch.model
        batch.ai_error_code = classification.error_code
    batch.status = "previewed"
    batch.updated_at = datetime.now(UTC)


def _load_profile(
    db: Session, bank_name: str | None, headers_hash: str
) -> ImportMappingProfile | None:
    if bank_name:
        return import_batch_repository.get_profile(db, bank_name, headers_hash)
    return import_batch_repository.latest_profile_for_headers(db, headers_hash)


def _normalize_bank_name(bank_name: str | None) -> str | None:
    if not bank_name:
        return None
    cleaned = " ".join(bank_name.split())[:100]
    return cleaned or None


def preview_import(
    db: Session,
    *,
    content: bytes,
    filename: str | None,
    content_type: str | None,
    bank_name: str | None,
    classifier: Classifier,
) -> ImportPreviewResponse:
    """Đọc file, đoán mapping, chuẩn hoá + đánh dấu trùng, gợi ý phân loại; lưu batch `previewed`.
    File (cùng nội dung) đã commit → 409 `IMPORT_ALREADY_COMMITTED`. Không tạo giao dịch."""
    name = clean_filename(filename)
    digest = import_parsing.file_hash(content)
    existing = import_batch_repository.get_by_file_hash(db, digest) if content else None
    if existing is not None and existing.status == "committed":
        raise ImportAlreadyCommitted(existing)

    table = read_table(content, name, content_type)
    header_index = import_parsing.find_header_row(table.rows)
    headers = import_parsing.label_headers(table.rows[header_index])
    headers_hash = import_parsing.headers_hash(headers)
    bank = _normalize_bank_name(bank_name)

    profile = _load_profile(db, bank, headers_hash)
    profile_mapping = None
    if profile is not None:
        try:
            profile_mapping = ColumnMapping.model_validate(profile.column_mapping)
        except ValidationError:
            profile_mapping = None
        if profile_mapping and import_parsing.mapping_problems(profile_mapping, headers):
            profile_mapping = None
    if profile is not None and profile_mapping is not None:
        mapping = profile_mapping
        source: MappingSource = "profile"
    else:
        profile = None
        mapping = import_parsing.guess_mapping(headers)
        source = "guess"
    date_format: DateFormat = (
        profile.date_format  # type: ignore[assignment]
        if profile and profile.date_format
        else import_parsing.guess_date_format(
            import_parsing.column_values(table.rows, header_index, headers, mapping.date)
        )
    )
    amount_values: list[str] = []
    for column in (mapping.amount, mapping.debit, mapping.credit):
        amount_values += import_parsing.column_values(table.rows, header_index, headers, column)
    decimal_style: DecimalStyle = (
        profile.decimal_style  # type: ignore[assignment]
        if profile and profile.decimal_style
        else import_parsing.guess_decimal_style(amount_values)
    )

    file_info = ImportFileInfo(
        file_type=table.file_type,  # type: ignore[arg-type]
        size_bytes=len(content),
        encoding=table.encoding,
        separator=table.separator,
        separator_label=SEPARATOR_LABELS.get(table.separator) if table.separator else None,
        sheet_name=table.sheet_name,
        header_row=header_index + 1,
        headers=headers,
        warnings=table.warnings,
    )
    now = datetime.now(UTC)
    batch = existing or ImportBatch(id=uuid.uuid4(), file_hash=digest, created_at=now)
    batch.filename = name
    batch.file_type = table.file_type
    batch.file_size_bytes = len(content)
    batch.bank_name = bank
    batch.file_info = {
        **file_info.model_dump(mode="json"),
        "headers_hash": headers_hash,
        "profile_id": str(profile.id) if profile else None,
    }
    batch.source_rows = table.rows
    batch.ai_error_code = None
    _apply_preview(
        db,
        batch,
        mapping=mapping,
        date_format=date_format,
        decimal_style=decimal_style,
        mapping_source=source,
        classifier=classifier,
    )
    if existing is None:
        import_batch_repository.add(db, batch)
    db.commit()
    db.refresh(batch)
    logger.info(
        "import batch=%s type=%s rows=%d valid=%d duplicate=%d bad=%d mapping=%s ai_error=%s",
        batch.id,
        batch.file_type,
        batch.row_count,
        batch.valid_count,
        batch.duplicate_count,
        batch.bad_count,
        source,
        batch.ai_error_code,
    )
    return build_preview(batch)


def update_mapping(
    db: Session, batch_id: uuid.UUID, data: ImportMappingUpdate, classifier: Classifier
) -> ImportPreviewResponse:
    """User đổi mapping cột / định dạng ngày / kiểu số → chuẩn hoá lại từ bảng thô đã lưu.
    Đề xuất phân loại cũ được giữ theo (nội dung, chiều); chỉ dòng mới mới gọi AI."""
    batch = get_batch(db, batch_id)
    if batch.status == "committed":
        raise ImportAlreadyCommitted(batch)
    info = _file_info(batch)
    problems = import_parsing.mapping_problems(data.column_mapping, info.headers)
    if problems:
        raise DomainError(" ".join(problems), "invalid_mapping")
    mapping = data.column_mapping
    header_index = info.header_row - 1
    source_rows = batch.source_rows or []
    previous = _stored_mapping(batch)
    # Đổi cột ngày / số tiền mà định dạng gửi lên vẫn là định dạng cũ (UI luôn gửi giá trị đang
    # hiển thị) → đoán lại theo cột mới; user chủ động chọn định dạng khác → dùng lựa chọn đó.
    date_changed = mapping.date != previous.date
    amount_changed = (mapping.amount, mapping.debit, mapping.credit) != (
        previous.amount,
        previous.debit,
        previous.credit,
    )
    date_format = data.date_format
    if not date_format or (date_changed and date_format == batch.date_format):
        date_format = import_parsing.guess_date_format(
            import_parsing.column_values(source_rows, header_index, info.headers, mapping.date)
        )
    amount_values: list[str] = []
    for column in (mapping.amount, mapping.debit, mapping.credit):
        amount_values += import_parsing.column_values(
            source_rows, header_index, info.headers, column
        )
    decimal_style = data.decimal_style
    if not decimal_style or (amount_changed and decimal_style == batch.decimal_style):
        decimal_style = import_parsing.guess_decimal_style(amount_values)
    cache = {
        (row.note.lower(), row.direction): row
        for row in stored_rows(batch)
        if row.status == "valid" and row.direction and row.suggested_category_id
    }
    _apply_preview(
        db,
        batch,
        mapping=mapping,
        date_format=date_format,
        decimal_style=decimal_style,
        mapping_source="user",
        classifier=classifier,
        cache=cache,
    )
    db.commit()
    db.refresh(batch)
    return build_preview(batch)


# ---------- commit ----------


def _ai_suggestion(row: ImportPreviewRow, batch: ImportBatch) -> dict[str, Any] | None:
    """Đề xuất gốc (trước khi user sửa) — chỉ khi đến từ sở thích đã học / AI."""
    if row.suggestion_source not in ("preference", "ai") or row.suggested_category_id is None:
        return None
    return {
        "category_id": str(row.suggested_category_id),
        "spending_type": row.suggested_spending_type,
        "confidence": row.confidence,
        "reason": row.reason,
        "matched_preference_id": str(row.matched_preference_id)
        if row.matched_preference_id
        else None,
        "note": row.note,
        "source": row.suggestion_source,
        "model": batch.model if row.suggestion_source == "ai" else "classification_preference",
    }


def _raw_input(batch: ImportBatch, row: ImportPreviewRow) -> str:
    description = row.raw.get("description") or row.note
    return f"Sao kê {batch.filename} · dòng {row.row_index}: {description}"[:MAX_RAW_INPUT]


def _record_classification(db: Session, transaction: Transaction) -> None:
    """Không sửa đề xuất → tăng `hit_count` của sở thích đã dùng (Phase 3). Có sửa → chỉ lưu
    feedback, **không** tự học sở thích mới (nội dung sao kê nhiễu, sửa hàng loạt dễ học sai)."""
    suggestion = transaction.ai_suggestion or {}
    if (
        suggestion.get("category_id") == str(transaction.category_id)
        and suggestion.get("spending_type") == transaction.spending_type
    ):
        classification_preference_service.record_feedback(db, transaction)
        return
    try:
        ai_category_id = uuid.UUID(str(suggestion.get("category_id")))
    except ValueError:
        return
    classification_feedback_repository.add(
        db,
        ClassificationFeedback(
            transaction_id=transaction.id,
            ai_category_id=ai_category_id,
            ai_spending_type=suggestion.get("spending_type"),
            final_category_id=transaction.category_id,
            final_spending_type=transaction.spending_type,
        ),
    )


def _save_profile(db: Session, batch: ImportBatch, now: datetime) -> None:
    info = batch.file_info or {}
    headers_hash = info.get("headers_hash")
    mapping = _stored_mapping(batch)
    if not headers_hash or import_parsing.mapping_problems(mapping, info.get("headers") or []):
        return
    bank = batch.bank_name or ""
    profile = import_batch_repository.get_profile(db, bank, headers_hash)
    if profile is None:
        profile = import_batch_repository.add_profile(
            db,
            ImportMappingProfile(
                bank_name=bank,
                headers_hash=headers_hash,
                column_mapping=mapping.model_dump(exclude_none=True),
            ),
        )
    profile.headers = info.get("headers")
    profile.column_mapping = mapping.model_dump(exclude_none=True)
    profile.date_format = batch.date_format
    profile.decimal_style = batch.decimal_style
    profile.last_used_at = now
    db.flush()


def commit_import(
    db: Session, batch_id: uuid.UUID, data: ImportCommitRequest
) -> ImportCommitResult:
    """Tạo giao dịch cho các dòng hợp lệ user đã chọn — 1 commit (lỗi → không ghi gì). Dòng trùng
    (trong file / đã import) và dòng lỗi bị bỏ qua."""
    batch = get_batch(db, batch_id)
    if batch.status == "committed":
        raise ImportAlreadyCommitted(batch)
    if batch.status not in EDITABLE_STATUSES:
        raise ConflictError("Lô import này không còn ở bước xem trước", "import_not_previewed")

    rows = {row.row_index: row for row in stored_rows(batch)}
    missing = [r.row_index for r in data.rows if r.row_index not in rows]
    if missing:
        raise DomainError(
            f"Không có dòng {', '.join(map(str, missing[:5]))} trong lô import này",
            "import_row_not_found",
        )
    chosen = [
        (rows[request.row_index], request)
        for request in sorted(data.rows, key=lambda r: r.row_index)
        if request.selected and rows[request.row_index].status == "valid"
    ]
    if not chosen:
        raise DomainError("Bạn chưa chọn dòng hợp lệ nào để nhập.", "no_rows_selected")

    already = transaction_repository.existing_dedup_hashes(
        db, {row.dedup_hash for row, _ in chosen if row.dedup_hash}
    )
    # Kiểm tra hết trước khi ghi: một dòng sai → 422, không giao dịch nào được tạo.
    planned = []
    late_duplicates = 0
    for row, request in chosen:
        if row.dedup_hash in already:
            late_duplicates += 1
            continue
        try:
            category = transaction_service.resolve_category(db, request.category_id, row.direction)  # type: ignore[arg-type]
            spending_type = transaction_service.resolve_spending_type(
                row.direction,  # type: ignore[arg-type]
                request.spending_type,
                category,
            )
        except DomainError as exc:
            raise DomainError(f"Dòng {row.row_index}: {exc.detail}", exc.code) from exc
        planned.append((row, request, category, spending_type))

    created: list[Transaction] = []
    try:
        for row, request, category, spending_type in planned:
            note = request.note if "note" in request.model_fields_set else row.note
            transaction = Transaction(
                id=uuid.uuid4(),
                direction=row.direction,
                amount=row.amount,
                occurred_on=row.occurred_on,
                note=note or None,
                category=category,
                spending_type=spending_type,
                source="import",
                raw_input=_raw_input(batch, row),
                ai_suggestion=_ai_suggestion(row, batch),
                import_batch_id=batch.id,
                dedup_hash=row.dedup_hash,
            )
            db.add(transaction)
            created.append(transaction)
        db.flush()
        for transaction in created:
            if transaction.ai_suggestion:
                _record_classification(db, transaction)

        now = datetime.now(UTC)
        batch.status = "committed"
        batch.committed_count = len(created)
        batch.committed_at = now
        batch.updated_at = now
        if data.save_mapping_profile:
            _save_profile(db, batch, now)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("import batch=%s commit integrity error: %s", batch.id, exc.orig)
        raise ConflictError(
            "Một số dòng vừa được import ở nơi khác — bạn tải lại bản xem trước rồi thử lại nhé.",
            "import_conflict",
        ) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(batch)

    valid_total = sum(1 for row in rows.values() if row.status == "valid")
    logger.info(
        "import batch=%s committed created=%d late_duplicates=%d",
        batch.id,
        len(created),
        late_duplicates,
    )
    return ImportCommitResult(
        created_count=len(created),
        skipped_duplicate_count=batch.duplicate_count + late_duplicates,
        bad_count=batch.bad_count,
        not_selected_count=valid_total - len(chosen),
        batch=ImportBatchRead.model_validate(batch),
    )


def list_mapping_profiles(db: Session, bank_name: str | None) -> list[ImportMappingProfile]:
    return import_batch_repository.list_profiles(db, _normalize_bank_name(bank_name))
