import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.ai import classifier
from app.api import embedding_hook
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.imports import (
    BankName,
    ImportClassifyItem,
    ImportCommitRequest,
    ImportCommitResult,
    ImportConflictResponse,
    ImportMappingProfileList,
    ImportMappingProfileRead,
    ImportMappingUpdate,
    ImportPreviewResponse,
)
from app.services import import_reader, import_service
from app.services.import_service import Classifier

router = APIRouter(prefix="/imports", tags=["imports"])


def _classifier(db: Session) -> Classifier:
    def classify(items: list[ImportClassifyItem]):
        return classifier.classify_batch_import(db, items)

    return classify


@router.post(
    "/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ImportConflictResponse, "description": "File đã được import (commit)"},
        413: {"model": ErrorResponse, "description": "File lớn hơn 10MB"},
        415: {"model": ErrorResponse, "description": "Không phải .csv / .xlsx"},
        422: {"model": ErrorResponse},
    },
)
def preview_import(
    db: DbSession,
    file: Annotated[UploadFile, File(description="Sao kê .csv hoặc .xlsx (≤ 10MB)")],
    bank_name: Annotated[BankName | None, Form(description="Tên ngân hàng (tuỳ chọn)")] = None,
):
    """Đọc sao kê, đoán mapping cột (hoặc dùng mapping đã lưu cho ngân hàng / bộ cột này), chuẩn
    hoá + đánh dấu dòng trùng / lỗi, gợi ý danh mục (sở thích đã học → AI 20 dòng / request).
    **Không tạo giao dịch** — user kiểm tra rồi gọi `POST /imports/{id}/commit`. Nội dung giao dịch
    (đã che số tài khoản / mã dài) được gửi tới OpenAI để phân loại."""
    filename = import_reader.clean_filename(file.filename)
    import_reader.check_declared_type(file.content_type, filename)
    if file.size is not None and file.size > import_reader.MAX_IMPORT_BYTES:
        raise import_reader.ImportFileTooLarge()
    content = file.file.read(import_reader.MAX_IMPORT_BYTES + 1)
    return import_service.preview_import(
        db,
        content=content,
        filename=filename,
        content_type=file.content_type,
        bank_name=bank_name,
        classifier=_classifier(db),
    )


@router.get(
    "/mapping-profiles",
    response_model=ImportMappingProfileList,
    responses={422: {"model": ErrorResponse}},
)
def list_mapping_profiles(
    db: DbSession,
    bank_name: Annotated[str | None, Query(max_length=100)] = None,
):
    """Mapping cột đã lưu (theo ngân hàng + bộ tiêu đề cột), dùng gần nhất trước."""
    profiles = import_service.list_mapping_profiles(db, bank_name)
    return ImportMappingProfileList(
        items=[ImportMappingProfileRead.model_validate(p) for p in profiles]
    )


@router.get(
    "/{batch_id}", response_model=ImportPreviewResponse, responses={404: {"model": ErrorResponse}}
)
def get_import(db: DbSession, batch_id: uuid.UUID):
    """Lô import + các dòng preview đã lưu tạm (kể cả sau khi commit)."""
    return import_service.get_preview(db, batch_id)


@router.patch(
    "/{batch_id}/mapping",
    response_model=ImportPreviewResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ImportConflictResponse},
        422: {"model": ErrorResponse},
    },
)
def update_mapping(db: DbSession, batch_id: uuid.UUID, data: ImportMappingUpdate):
    """Đổi mapping cột / định dạng ngày / kiểu số tiền → chuẩn hoá lại preview (giữ đề xuất phân
    loại cũ cho nội dung đã phân loại). Không tạo giao dịch."""
    return import_service.update_mapping(db, batch_id, data, _classifier(db))


@router.post(
    "/{batch_id}/commit",
    response_model=ImportCommitResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ImportConflictResponse},
        422: {"model": ErrorResponse},
    },
)
def commit_import(db: DbSession, batch_id: uuid.UUID, data: ImportCommitRequest):
    """Tạo giao dịch `source='import'` cho các dòng hợp lệ đã chọn (danh mục / loại chi tiêu / ghi
    chú user đã sửa) trong **một** DB transaction; bỏ qua dòng trùng / lỗi; lưu mapping profile."""
    result = import_service.commit_import(db, batch_id, data)
    embedding_hook.index_import_batch(db, batch_id)
    return result
