import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.ai import advice_writer
from app.core.db import DbSession
from app.models.enums import AdviceStatus
from app.schemas.budget_advice import (
    AdvisorSettings,
    AdvisorSettingsUpdate,
    BudgetAdviceAcceptRequest,
    BudgetAdviceAcceptResult,
    BudgetAdviceDismissRequest,
    BudgetAdviceGenerateRequest,
    BudgetAdviceList,
    BudgetAdviceRead,
)
from app.schemas.common import ErrorResponse
from app.services import budget_advice_service

router = APIRouter(prefix="/budget/advice", tags=["budget-advice"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}
CONFLICT = {409: {"model": ErrorResponse}}


@router.get("/settings", response_model=AdvisorSettings)
def get_advisor_settings(db: DbSession):
    """Ngưỡng decision tree (`app_settings.budget_advisor`)."""
    return budget_advice_service.get_settings(db)


@router.patch(
    "/settings", response_model=AdvisorSettings, responses={422: {"model": ErrorResponse}}
)
def update_advisor_settings(db: DbSession, data: AdvisorSettingsUpdate):
    """Sửa một phần ngưỡng; chỉ áp dụng cho advice tạo / tính lại sau đó."""
    return budget_advice_service.update_settings(db, data)


@router.get("", response_model=BudgetAdviceList, responses={422: {"model": ErrorResponse}})
def list_budget_advice(
    db: DbSession,
    month: Annotated[date | None, Query(description="Một ngày trong tháng, vd 2026-10-01")] = None,
    status: Annotated[AdviceStatus | None, Query(description="open | accepted | dismissed")] = None,
    allocation_id: Annotated[uuid.UUID | None, Query()] = None,
):
    """Danh sách advice (tháng mới nhất trước, trong tháng theo thứ tự dòng ngân sách)."""
    items = budget_advice_service.list_advice(
        db, month=month, status=status, allocation_id=allocation_id
    )
    return BudgetAdviceList(items=[budget_advice_service.to_read(a) for a in items])


@router.post("/generate", response_model=BudgetAdviceList, responses=ERRORS)
def generate_budget_advice(db: DbSession, data: BudgetAdviceGenerateRequest):
    """Tạo advice cho các dòng (trừ nhóm tiết kiệm) của budget active / closed tháng `month`.

    Verdict + evidence deterministic (`advisor_rules`); AI (model fast) chỉ viết explanation —
    AI lỗi → template. Dòng đã có advice `open` giữ nguyên trừ khi `regenerate`; dòng đã
    accepted / dismissed không tạo lại. Trả mọi advice của tháng (lọc theo `allocation_id`)."""
    drafts = budget_advice_service.prepare_advice(
        db,
        data.month,
        today=data.today or date.today(),
        allocation_id=data.allocation_id,
        regenerate=data.regenerate,
    )
    texts = advice_writer.write_explanations([(d.verdict, d.evidence) for d in drafts])
    budget_advice_service.save_advice(db, drafts, texts)
    items = budget_advice_service.list_advice(
        db, month=data.month, allocation_id=data.allocation_id
    )
    return BudgetAdviceList(items=[budget_advice_service.to_read(a) for a in items])


@router.post(
    "/{advice_id}/accept",
    response_model=BudgetAdviceAcceptResult,
    responses={**ERRORS, **CONFLICT},
)
def accept_budget_advice(db: DbSession, advice_id: uuid.UUID, data: BudgetAdviceAcceptRequest):
    """User xác nhận (`confirm: true`) áp dụng `proposed_planned_amount` cho dòng cùng danh mục /
    hũ ở budget tháng `target_month` (mặc định tháng sau; chưa có budget → tạo nháp copy từ tháng
    của advice). Chỉ cho advice `adjust_budget` đang `open`."""
    return budget_advice_service.accept_advice(db, advice_id, data)


@router.post(
    "/{advice_id}/dismiss",
    response_model=BudgetAdviceRead,
    responses={**ERRORS, **CONFLICT},
)
def dismiss_budget_advice(db: DbSession, advice_id: uuid.UUID, data: BudgetAdviceDismissRequest):
    """Bỏ qua advice (kèm lý do tuỳ chọn); không đổi ngân sách."""
    return budget_advice_service.to_read(budget_advice_service.dismiss_advice(db, advice_id, data))
