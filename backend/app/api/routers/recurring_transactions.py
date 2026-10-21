import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.recurring import (
    RecurringCreate,
    RecurringDetectRequest,
    RecurringList,
    RecurringRead,
    RecurringSuggestionConfirm,
    RecurringSuggestionList,
    RecurringTransactionCreate,
    RecurringTransactionResult,
    RecurringUpdate,
)
from app.schemas.transaction import TransactionRead
from app.services import goal_service, recurring_service

router = APIRouter(prefix="/recurring-transactions", tags=["recurring-transactions"])

NOT_FOUND = {404: {"model": ErrorResponse}}
INVALID = {422: {"model": ErrorResponse}}
CONFLICT = {409: {"model": ErrorResponse}}

Today = Annotated[
    date | None,
    Query(description="Hôm nay phía user (mặc định của server) — dùng cho demo/test"),
]


def _today(today: date | None) -> date:
    return today or date.today()


@router.get("", response_model=RecurringList)
def list_recurring(
    db: DbSession,
    active: Annotated[bool | None, Query(description="Lọc theo trạng thái bật / tắt")] = None,
    today: Today = None,
):
    """Khoản định kỳ kèm trạng thái đến hạn (đang bật trước, kỳ gần nhất trước)."""
    return recurring_service.list_recurring(db, _today(today), active)


@router.post(
    "", response_model=RecurringRead, status_code=status.HTTP_201_CREATED, responses=INVALID
)
def create_recurring(db: DbSession, data: RecurringCreate, today: Today = None):
    """Tạo khoản định kỳ thủ công (tiền nhà, internet, lương…). Không tạo giao dịch."""
    return recurring_service.create_recurring(db, data, _today(today))


# Khai báo trước "/{recurring_id}" để các đường dẫn tĩnh không bị hiểu là id.
@router.post("/detect", response_model=RecurringSuggestionList, responses=INVALID)
def detect_recurring(db: DbSession, data: RecurringDetectRequest, today: Today = None):
    """Phát hiện mẫu định kỳ từ lịch sử (deterministic). **Chỉ tạo đề xuất** — user xác nhận
    qua `…/suggestions/{id}/confirm`."""
    return recurring_service.detect(db, data, _today(today))


@router.get("/suggestions", response_model=RecurringSuggestionList)
def list_suggestions(db: DbSession):
    """Đề xuất của lần phát hiện gần nhất (bỏ mẫu đã có khoản định kỳ)."""
    return recurring_service.list_suggestions(db)


@router.post(
    "/suggestions/{suggestion_id}/confirm",
    response_model=RecurringRead,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **INVALID},
)
def confirm_suggestion(
    db: DbSession,
    suggestion_id: uuid.UUID,
    data: RecurringSuggestionConfirm,
    today: Today = None,
):
    """User xác nhận đề xuất → tạo khoản định kỳ (`auto_detected`) + gắn giao dịch lịch sử."""
    return recurring_service.confirm_suggestion(db, suggestion_id, data, _today(today))


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
def dismiss_suggestion(db: DbSession, suggestion_id: uuid.UUID) -> Response:
    """Từ chối đề xuất — lần phát hiện sau không đề xuất lại mẫu này."""
    recurring_service.dismiss_suggestion(db, suggestion_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{recurring_id}", response_model=RecurringRead, responses={**NOT_FOUND, **INVALID})
def update_recurring(
    db: DbSession, recurring_id: uuid.UUID, data: RecurringUpdate, today: Today = None
):
    """Sửa / tạm dừng (`active: false`) / bật lại."""
    return recurring_service.update_recurring(db, recurring_id, data, _today(today))


@router.delete(
    "/{recurring_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
def deactivate_recurring(db: DbSession, recurring_id: uuid.UUID) -> Response:
    """Tắt khoản định kỳ (giữ lịch sử giao dịch đã gắn)."""
    recurring_service.deactivate_recurring(db, recurring_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{recurring_id}/create-transaction",
    response_model=RecurringTransactionResult,
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **INVALID, **CONFLICT},
)
def create_transaction(
    db: DbSession,
    recurring_id: uuid.UUID,
    data: RecurringTransactionCreate,
    today: Today = None,
):
    """Ghi kỳ đang đến hạn thành giao dịch thật (`source = "recurring"`, `recurring_id`) và chuyển
    khoản định kỳ sang kỳ sau. Thu nhập: kèm `pyf_proposal` (chưa ghi gì)."""
    day = _today(today)
    transaction, recurring = recurring_service.create_transaction_from_recurring(
        db, recurring_id, data, day
    )
    return RecurringTransactionResult(
        transaction=TransactionRead.model_validate(transaction),
        recurring=recurring,
        pyf_proposal=goal_service.proposal_for_new_income(db, transaction, day),
    )
