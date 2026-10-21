import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.schemas.budget import BudgetAllocationRead
from app.schemas.common import ErrorResponse
from app.schemas.transaction import TransactionList, TransactionRead
from app.schemas.zone import ZoneUpdate
from app.services import analytics_service, zone_service

router = APIRouter(prefix="/budget-allocations", tags=["budgets"])


@router.patch(
    "/{allocation_id}/zone",
    response_model=BudgetAllocationRead,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def update_zone(db: DbSession, allocation_id: uuid.UUID, data: ZoneUpdate):
    """Đổi chế độ vùng linh hoạt của dòng: `manual` cần đủ `comfort_low <= comfort_high <=
    warning_threshold` (sai → 422 `invalid_zone_thresholds` / `zone_thresholds_required`);
    `auto` không nhận ngưỡng, backend tính lại ngay từ lịch sử 3–6 tháng (thiếu → % dự phòng).
    Dòng savings → 422 `allocation_not_tracked`; ngân sách đã đóng → 409 `budget_closed`."""
    return zone_service.update_zone(db, allocation_id, data)


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
