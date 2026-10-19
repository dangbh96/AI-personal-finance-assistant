import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.ai import preference_parser
from app.core.db import DbSession
from app.schemas.ai import PreferenceDraft
from app.schemas.classification import (
    PreferenceCreate,
    PreferenceList,
    PreferenceParseRequest,
    PreferenceRead,
)
from app.schemas.common import ErrorResponse
from app.services import classification_preference_service

router = APIRouter(prefix="/classification-preferences", tags=["classification-preferences"])


@router.get("", response_model=PreferenceList)
def list_preferences(
    db: DbSession,
    q: Annotated[
        str | None, Query(max_length=100, description="Tìm trong pattern / câu ví dụ")
    ] = None,
    category_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    items = classification_preference_service.list_preferences(
        db, q=q, category_id=category_id, limit=limit
    )
    return PreferenceList(items=[PreferenceRead.model_validate(p) for p in items])


@router.post(
    "",
    response_model=PreferenceRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_preference(db: DbSession, data: PreferenceCreate):
    """Lưu sở thích user đã xác nhận. Trùng pattern (sau chuẩn hoá) → cập nhật cái cũ."""
    return classification_preference_service.create_preference(db, data)


@router.post(
    "/parse",
    response_model=PreferenceDraft,
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse, "description": "AI trả kết quả không hợp lệ"},
        503: {"model": ErrorResponse, "description": "AI chưa cấu hình / không khả dụng"},
    },
)
def parse_preference(db: DbSession, data: PreferenceParseRequest):
    """Phân tích câu sở thích ("Tao coi giày là thiết yếu") thành draft. **Không lưu DB**."""
    return preference_parser.parse_preference(db, data.text)


@router.delete(
    "/{preference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}},
)
def delete_preference(db: DbSession, preference_id: uuid.UUID) -> Response:
    classification_preference_service.delete_preference(db, preference_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
