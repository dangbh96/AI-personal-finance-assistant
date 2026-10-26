import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.agents import review_graph
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.review import (
    PendingWeeklyReviewRead,
    ReflectionAnswerRead,
    ReflectionCreate,
    WeeklyReviewGenerateRequest,
    WeeklyReviewList,
    WeeklyReviewRead,
)
from app.services import review_service

router = APIRouter(prefix="/reviews/weekly", tags=["reviews"])

ERRORS = {404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}}


@router.get("", response_model=WeeklyReviewList, responses={422: {"model": ErrorResponse}})
def list_weekly_reviews(
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from", description="Từ tuần (bao gồm)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Đến tuần (bao gồm)")] = None,
):
    """Danh sách review tuần (lọc theo `week_start`), tuần mới nhất trước."""
    reviews = review_service.list_weekly(db, date_from, date_to)
    return WeeklyReviewList(items=review_service.to_reads(db, reviews))


# Khai báo các path cố định trước "/{week_start}".
@router.get("/pending", response_model=PendingWeeklyReviewRead)
def get_pending_weekly_review(
    db: DbSession,
    today: Annotated[
        date | None, Query(description="Hôm nay phía user (mặc định của server)")
    ] = None,
):
    """Gợi ý banner Thứ Hai: review tuần trước đang chờ. Không tự tạo review."""
    return review_service.pending_weekly(db, today or date.today())


@router.post(
    "",
    response_model=WeeklyReviewRead,
    responses={422: {"model": ErrorResponse}},
)
def generate_weekly_review(db: DbSession, data: WeeklyReviewGenerateRequest):
    """Tạo review on-demand. Tuần đã có review và `regenerate=false` → trả review cũ (không gọi AI).
    `regenerate=true` → tính lại metrics + narrative, status về `generated`, giữ reflection cũ.
    AI lỗi / output không qua kiểm tra → narrative dự phòng (`narrative.fallback_used = true`)."""
    review = review_graph.get_or_generate_weekly_review(
        db, data.week_start, today=data.today or date.today(), regenerate=data.regenerate
    )
    return review_service.to_read(db, review)


@router.get("/{week_start}", response_model=WeeklyReviewRead, responses=ERRORS)
def get_weekly_review(db: DbSession, week_start: date):
    """Review của tuần bắt đầu `week_start` (Thứ Hai); chưa có → 404."""
    return review_service.to_read(db, review_service.get_weekly_by_week_or_404(db, week_start))


@router.post(
    "/{review_id}/reflections",
    response_model=ReflectionAnswerRead,
    status_code=status.HTTP_201_CREATED,
    responses=ERRORS,
)
def add_reflection(db: DbSession, review_id: uuid.UUID, data: ReflectionCreate):
    """Lưu câu trả lời nhìn lại + giao dịch "không đáng tiền" (phải là khoản chi trong tuần);
    review chuyển `completed`."""
    return review_service.add_weekly_reflection(db, review_id, data)
