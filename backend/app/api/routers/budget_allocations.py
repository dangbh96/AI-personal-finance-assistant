import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.transaction import TransactionList, TransactionRead
from app.services import analytics_service

router = APIRouter(prefix="/budget-allocations", tags=["budgets"])


@router.get(
    "/{allocation_id}/transactions",
    response_model=TransactionList,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def list_allocation_transactions(
    db: DbSession,
    allocation_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Drill-down: giao dịch chi thuộc dòng phân bổ trong tháng của ngân sách, mới nhất trước.
    Dòng nhóm `savings` không có giao dịch."""
    items, total = analytics_service.list_allocation_transactions(
        db, allocation_id, page=page, page_size=page_size
    )
    return TransactionList(
        items=[TransactionRead.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )
