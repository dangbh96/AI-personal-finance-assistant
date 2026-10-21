import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.db import DbSession
from app.models.enums import GoalStatus
from app.schemas.common import ErrorResponse
from app.schemas.goal import (
    GoalContributionCreate,
    GoalContributionRead,
    GoalCreate,
    GoalDetail,
    GoalList,
    GoalRead,
    GoalUpdate,
    PyfAllocationRequest,
    PyfAllocationResult,
    PyfProposal,
    PyfProposalRequest,
    UnallocatedIncomeList,
)
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])

NOT_FOUND = {404: {"model": ErrorResponse}}
INVALID = {422: {"model": ErrorResponse}}
CONFLICT = {409: {"model": ErrorResponse}}

Today = Annotated[
    date | None,
    Query(description="Hôm nay phía user (mặc định của server) — dùng cho demo/test"),
]


def _today(today: date | None) -> date:
    return today or date.today()


@router.get("", response_model=GoalList, responses=INVALID)
def list_goals(
    db: DbSession,
    status_filter: Annotated[GoalStatus | None, Query(alias="status")] = None,
    today: Today = None,
):
    """Mục tiêu kèm số liệu tính sẵn (đang thực hiện → tạm dừng → đã đạt, theo priority)."""
    return goal_service.list_goals(db, _today(today), status_filter)


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED, responses=INVALID)
def create_goal(db: DbSession, data: GoalCreate, today: Today = None):
    return goal_service.create_goal(db, data, _today(today))


# Khai báo trước "/{goal_id}" để các đường dẫn tĩnh không bị hiểu là id.
@router.get("/unallocated-incomes", response_model=UnallocatedIncomeList, responses=INVALID)
def list_unallocated_incomes(db: DbSession, today: Today = None):
    """Thu nhập từ đầu tháng trước tới hôm nay chưa được phân bổ cho mục tiêu nào."""
    return goal_service.list_unallocated_incomes(db, _today(today))


@router.post("/pyf-proposal", response_model=PyfProposal, responses={**INVALID, **CONFLICT})
def propose_pyf_allocation(db: DbSession, data: PyfProposalRequest, today: Today = None):
    """Đề xuất Pay Yourself First cho một thu nhập đã lưu (hoặc tính lại với số user chỉnh).
    **Không ghi DB.** Thu nhập đã phân bổ → 409 `income_already_allocated`."""
    return goal_service.propose_pyf_allocation(db, data, _today(today))


@router.post(
    "/allocations",
    response_model=PyfAllocationResult,
    status_code=status.HTTP_201_CREATED,
    responses={**INVALID, **CONFLICT},
)
def confirm_allocations(db: DbSession, data: PyfAllocationRequest, today: Today = None):
    """User xác nhận phân bổ: tạo `goal_contributions` gắn thu nhập (lỗi → không ghi gì)."""
    return goal_service.confirm_allocations(db, data, _today(today))


@router.get("/{goal_id}", response_model=GoalDetail, responses=NOT_FOUND)
def get_goal(db: DbSession, goal_id: uuid.UUID, today: Today = None):
    """Mục tiêu + lịch sử khoản góp (mới nhất trước)."""
    return goal_service.get_goal_detail(db, goal_id, _today(today))


@router.patch("/{goal_id}", response_model=GoalRead, responses={**NOT_FOUND, **INVALID})
def update_goal(db: DbSession, goal_id: uuid.UUID, data: GoalUpdate, today: Today = None):
    return goal_service.update_goal(db, goal_id, data, _today(today))


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_goal(db: DbSession, goal_id: uuid.UUID) -> Response:
    """Xoá mục tiêu chưa có khoản góp, hoặc đã tạm dừng (xoá cả lịch sử góp); khác → 409."""
    goal_service.delete_goal(db, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{goal_id}/contributions",
    response_model=GoalContributionRead,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **INVALID},
)
def add_contribution(
    db: DbSession, goal_id: uuid.UUID, data: GoalContributionCreate, today: Today = None
):
    """Khoản góp thủ công (không gắn thu nhập), vd số tiền đã để dành sẵn."""
    return goal_service.add_contribution(db, goal_id, data, _today(today))


@router.delete(
    "/{goal_id}/contributions/{contribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
def delete_contribution(db: DbSession, goal_id: uuid.UUID, contribution_id: uuid.UUID) -> Response:
    goal_service.delete_contribution(db, goal_id, contribution_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
