import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.db import DbSession
from app.schemas.analytics import BudgetStatusRead, BudgetZoneList
from app.schemas.budget import (
    BudgetCopyRequest,
    BudgetCreate,
    BudgetJarList,
    BudgetList,
    BudgetPreviewRequest,
    BudgetPreviewResponse,
    BudgetRead,
    BudgetUpdate,
)
from app.schemas.common import ErrorResponse
from app.schemas.zone import ZoneRecalculateRequest
from app.services import analytics_service, budget_service, zone_service

router = APIRouter(prefix="/budgets", tags=["budgets"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}
CONFLICT = {409: {"model": ErrorResponse}}

TodayQuery = Annotated[
    date | None, Query(description="Ngày tính tiến độ tháng (mặc định hôm nay của server)")
]
MonthQuery = Annotated[
    date | None, Query(description="Một ngày trong tháng cần xem, vd. 2026-10-01")
]


@router.get("", response_model=BudgetList, responses={422: {"model": ErrorResponse}})
def list_budgets(
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from", description="Từ tháng (bao gồm)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Đến tháng (bao gồm)")] = None,
):
    """Danh sách ngân sách, tháng mới nhất trước."""
    budgets = budget_service.list_budgets(db, date_from=date_from, date_to=date_to)
    return BudgetList(items=[budget_service.to_read(b) for b in budgets])


# Khai báo các path cố định trước "/{budget_id}".
@router.get("/jars", response_model=BudgetJarList)
def list_jars(db: DbSession):
    """Hũ của strategy envelope và danh mục thuộc mỗi hũ (`budget_jar_category_map`)."""
    return budget_service.list_jars(db)


@router.post(
    "/preview", response_model=BudgetPreviewResponse, responses={422: {"model": ErrorResponse}}
)
def preview_budget(db: DbSession, data: BudgetPreviewRequest):
    """Tính phân bổ theo strategy (hoặc kiểm tra phân bổ đã chỉnh), tổng, cảnh báo và so sánh
    tham khảo 50/30/20. **Không lưu DB**."""
    return budget_service.preview_budget(db, data)


@router.post(
    "",
    response_model=BudgetRead,
    status_code=status.HTTP_201_CREATED,
    responses={**ERRORS, **CONFLICT},
)
def create_budget(db: DbSession, data: BudgetCreate):
    """Lưu ngân sách (draft hoặc active). Mỗi tháng 1 ngân sách — trùng tháng → 409."""
    return budget_service.to_read(budget_service.create_budget(db, data))


@router.post(
    "/copy-from-previous",
    response_model=BudgetRead,
    status_code=status.HTTP_201_CREATED,
    responses={**ERRORS, **CONFLICT},
)
def copy_from_previous(db: DbSession, data: BudgetCopyRequest):
    """Copy ngân sách tháng trước (hoặc `from_month`) sang `to_month`, trạng thái draft."""
    budget = budget_service.copy_from_previous_month(
        db, to_month=data.to_month, from_month=data.from_month
    )
    return budget_service.to_read(budget)


@router.get("/current/status", response_model=BudgetStatusRead, responses=ERRORS)
def get_current_status(db: DbSession, month: MonthQuery = None, today: TodayQuery = None):
    """Planned vs actual của ngân sách **active/closed** của tháng (mặc định tháng chứa `today`).
    Tháng chưa có ngân sách → 404 `budget_not_found`; ngân sách nháp → 404 `budget_not_active`."""
    return analytics_service.get_current_status(db, today or date.today(), month)


@router.get("/{budget_id}", response_model=BudgetRead, responses=ERRORS)
def get_budget(db: DbSession, budget_id: uuid.UUID):
    return budget_service.to_read(budget_service.get_budget(db, budget_id))


@router.get("/{budget_id}/status", response_model=BudgetStatusRead, responses=ERRORS)
def get_budget_status(db: DbSession, budget_id: uuid.UUID, today: TodayQuery = None):
    """Planned / actual / variance / used % / pace / top contributor / vùng linh hoạt từng dòng
    phân bổ và tổng tháng. Deterministic, không dùng AI."""
    return analytics_service.get_budget_status_by_id(db, budget_id, today or date.today())


@router.get("/{budget_id}/zones", response_model=BudgetZoneList, responses=ERRORS)
def get_budget_zones(db: DbSession, budget_id: uuid.UUID, today: TodayQuery = None):
    """Vùng linh hoạt (🟢 normal / 🟡 attention / 🔴 review_needed) + cảnh báo pro-rata của mọi dòng
    chi tiêu; dòng auto kèm cách tính ngưỡng (lịch sử 3–6 tháng, không tính khoản bất thường).
    Deterministic, không dùng AI."""
    return analytics_service.get_budget_zones(db, budget_id, today or date.today())


@router.post(
    "/{budget_id}/zones/recalculate",
    response_model=BudgetZoneList,
    responses={**ERRORS, **CONFLICT},
)
def recalculate_zones(
    db: DbSession,
    budget_id: uuid.UUID,
    data: ZoneRecalculateRequest | None = None,
    today: TodayQuery = None,
):
    """Tính lại và lưu ngưỡng các dòng auto (`allocation_ids = null` → mọi dòng chi tiêu); dòng
    manual giữ nguyên. Idempotent. Ngân sách đã đóng → 409 `budget_closed`."""
    ids = data.allocation_ids if data else None
    zone_service.recalculate_auto_zones(db, budget_id, ids)
    return analytics_service.get_budget_zones(db, budget_id, today or date.today())


@router.patch("/{budget_id}", response_model=BudgetRead, responses={**ERRORS, **CONFLICT})
def update_budget(db: DbSession, budget_id: uuid.UUID, data: BudgetUpdate):
    """Sửa thu nhập dự kiến / trạng thái / phân bổ (gửi `allocations` = thay toàn bộ)."""
    return budget_service.to_read(budget_service.update_budget(db, budget_id, data))


@router.delete(
    "/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}, **CONFLICT},
)
def delete_budget(db: DbSession, budget_id: uuid.UUID) -> Response:
    """Chỉ xoá được ngân sách draft."""
    budget_service.delete_budget(db, budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
