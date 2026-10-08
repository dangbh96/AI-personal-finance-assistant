import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.db import DbSession
from app.models.enums import Direction
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import ErrorResponse
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: DbSession,
    kind: Direction | None = None,
    include_archived: Annotated[bool, Query()] = False,
):
    return category_service.list_categories(db, kind=kind, include_archived=include_archived)


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_category(db: DbSession, data: CategoryCreate):
    return category_service.create_category(db, data)


@router.patch("/{category_id}", response_model=CategoryRead, responses=ERRORS)
def update_category(db: DbSession, category_id: uuid.UUID, data: CategoryUpdate):
    return category_service.update_category(db, category_id, data)
