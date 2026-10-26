import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.agents import review_graph
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.review import (
    MonthlyReviewGenerateRequest,
    MonthlyReviewList,
    MonthlyReviewMetrics,
    MonthlyReviewRead,
    ReflectionAnswerRead,
    ReflectionCreate,
)
from app.services import analytics_service, review_service
from app.services.money import month_range

router = APIRouter(prefix="/reviews/monthly", tags=["reviews"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("", response_model=MonthlyReviewList, responses={422: {"model": ErrorResponse}})
def list_monthly_reviews(
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from", description="Từ tháng (bao gồm)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Đến tháng (bao gồm)")] = None,
):
    """Danh sách review tháng (lọc theo `month`), tháng mới nhất trước."""
    reviews = review_service.list_monthly(db, date_from, date_to)
    return MonthlyReviewList(items=review_service.to_monthly_reads(db, reviews))


@router.post("", response_model=MonthlyReviewRead, responses={422: {"model": ErrorResponse}})
def generate_monthly_review(db: DbSession, data: MonthlyReviewGenerateRequest):
    """Tạo review tháng on-demand (cùng LangGraph `review_graph` với review tuần).
    Tháng đã có review và `regenerate=false` → trả review cũ (không gọi AI).
    `regenerate=true` → tính lại metrics + narrative, status về `generated`, giữ reflection cũ.
    AI lỗi / output không qua kiểm tra → narrative dự phòng (`narrative.fallback_used = true`)."""
    review = review_graph.get_or_generate_monthly_review(
        db, data.month, today=data.today or date.today(), regenerate=data.regenerate
    )
    return review_service.to_monthly_read(db, review)


@router.get(
    "/{month}/metrics",
    response_model=MonthlyReviewMetrics,
    responses={422: {"model": ErrorResponse}},
)
def preview_monthly_metrics(
    db: DbSession,
    month: date,
    today: Annotated[
        date | None, Query(description="Hôm nay phía user (mặc định của server)")
    ] = None,
):
    """Xem trước metrics deterministic của tháng chứa `month` (không gọi AI, không lưu)."""
    return analytics_service.preview_review_metrics(
        db, "month", month_range(month)[0], today or date.today()
    )


@router.get("/{month}", response_model=MonthlyReviewRead, responses=ERRORS)
def get_monthly_review(db: DbSession, month: date):
    """Review của tháng chứa `month` (vd `2026-10-01`); chưa có → 404."""
    return review_service.to_monthly_read(
        db, review_service.get_monthly_by_month_or_404(db, month_range(month)[0])
    )


@router.post(
    "/{review_id}/reflections",
    response_model=ReflectionAnswerRead,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
def add_monthly_reflection(db: DbSession, review_id: uuid.UUID, data: ReflectionCreate):
    """Lưu câu trả lời nhìn lại tháng + giao dịch muốn nhìn lại (phải là khoản chi trong tháng);
    review chuyển `completed`."""
    return review_service.add_monthly_reflection(db, review_id, data)
