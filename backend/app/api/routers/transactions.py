import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.ai import nl_transaction_parser
from app.core.db import DbSession
from app.models.enums import Direction, SpendingType
from app.schemas.ai import TransactionParseRequest, TransactionParseResponse
from app.schemas.common import ErrorResponse
from app.schemas.transaction import (
    TransactionCreate,
    TransactionList,
    TransactionRead,
    TransactionSummary,
    TransactionUpdate,
)
from app.services import transaction_service
from app.services.transaction_service import TransactionFilters

router = APIRouter(prefix="/transactions", tags=["transactions"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


def transaction_filters(
    date_from: Annotated[date | None, Query(alias="from", description="Từ ngày (bao gồm)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Đến ngày (bao gồm)")] = None,
    category_id: uuid.UUID | None = None,
    spending_type: SpendingType | None = None,
    direction: Direction | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Tìm trong ghi chú")] = None,
) -> TransactionFilters:
    return TransactionFilters(
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        spending_type=spending_type,
        direction=direction,
        q=q.strip() if q else None,
    )


Filters = Annotated[TransactionFilters, Depends(transaction_filters)]


@router.get("", response_model=TransactionList, responses={422: {"model": ErrorResponse}})
def list_transactions(
    db: DbSession,
    filters: Filters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    items, total = transaction_service.list_transactions(
        db, filters, page=page, page_size=page_size
    )
    return TransactionList(
        items=[TransactionRead.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# Khai báo trước "/{transaction_id}" để "summary" không bị hiểu là id.
@router.get(
    "/summary", response_model=TransactionSummary, responses={422: {"model": ErrorResponse}}
)
def summarize_transactions(db: DbSession, filters: Filters):
    return transaction_service.summarize(db, filters)


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_transaction(db: DbSession, data: TransactionCreate):
    return transaction_service.create_transaction(db, data)


@router.post(
    "/parse",
    response_model=TransactionParseResponse,
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse, "description": "AI trả kết quả không hợp lệ"},
        503: {"model": ErrorResponse, "description": "AI chưa cấu hình / không khả dụng"},
    },
)
def parse_transactions(db: DbSession, data: TransactionParseRequest):
    """Phân tích câu tự nhiên thành draft giao dịch. **Không lưu DB** — user xác nhận rồi mới
    gọi `POST /transactions` với `source="nl"`, `raw_input`, `ai_suggestion`."""
    return nl_transaction_parser.parse_transactions(
        db, data.text, today=data.today, timezone=data.timezone
    )


@router.get("/{transaction_id}", response_model=TransactionRead, responses=ERRORS)
def get_transaction(db: DbSession, transaction_id: uuid.UUID):
    return transaction_service.get_transaction(db, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionRead, responses=ERRORS)
def update_transaction(db: DbSession, transaction_id: uuid.UUID, data: TransactionUpdate):
    return transaction_service.update_transaction(db, transaction_id, data)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}},
)
def delete_transaction(db: DbSession, transaction_id: uuid.UUID) -> Response:
    transaction_service.delete_transaction(db, transaction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
