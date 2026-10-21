"""Lưu / đọc Weekly review và reflection (Phase 6) — deterministic, không gọi AI.

Việc tạo narrative (LangGraph + OpenAI) nằm ở `agents/review_graph`; service này chỉ lưu kết quả đã
qua kiểm tra, quản lý trạng thái `generated → completed` và validate reflection.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import ReflectionAnswer, WeeklyReview
from app.repositories import review_repository, transaction_repository
from app.schemas.review import (
    PendingWeeklyReviewRead,
    ReflectionAnswerRead,
    ReflectionCreate,
    ReviewMetrics,
    ReviewNarrative,
    WeeklyReviewRead,
)
from app.services.money import week_range

WEEKLY = "weekly"


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def ensure_week_started(week_start: date, today: date) -> None:
    if week_start.weekday() != 0:
        raise DomainError("Tuần phải bắt đầu vào Thứ Hai", "week_start_not_monday")
    if week_start > today:
        raise DomainError("Tuần này chưa bắt đầu — chưa thể tạo review", "week_not_started")


def get_weekly_by_week(db: Session, week_start: date) -> WeeklyReview | None:
    return review_repository.get_weekly_by_week(db, week_start)


def get_weekly_by_week_or_404(db: Session, week_start: date) -> WeeklyReview:
    review = review_repository.get_weekly_by_week(db, week_start)
    if review is None:
        raise NotFoundError(
            f"Chưa có review cho tuần bắt đầu {week_start:%d/%m/%Y}", "weekly_review_not_found"
        )
    return review


def get_weekly(db: Session, review_id: uuid.UUID) -> WeeklyReview:
    review = review_repository.get_weekly(db, review_id)
    if review is None:
        raise NotFoundError("Không tìm thấy review tuần", "weekly_review_not_found")
    return review


def list_weekly(
    db: Session, date_from: date | None = None, date_to: date | None = None
) -> list[WeeklyReview]:
    if date_from and date_to and date_from > date_to:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")
    return review_repository.list_weekly(db, date_from, date_to)


def save_weekly_review(
    db: Session,
    week_start: date,
    metrics: ReviewMetrics,
    narrative: ReviewNarrative,
    model: str | None,
) -> WeeklyReview:
    """Tạo mới hoặc ghi đè (regenerate) metrics + narrative; trạng thái về `generated`.
    Reflection cũ được giữ nguyên."""
    review = review_repository.get_weekly_by_week(db, week_start)
    if review is None:
        review = WeeklyReview(week_start=week_start)
        db.add(review)
    review.metrics = metrics.model_dump(mode="json")
    review.narrative = narrative.model_dump(mode="json")
    review.model = model
    review.status = "generated"
    db.commit()
    db.refresh(review)
    return review


def _validate_flagged(db: Session, review: WeeklyReview, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    ids = list(dict.fromkeys(ids))
    found = {t.id: t for t in transaction_repository.get_many(db, ids)}
    missing = [i for i in ids if i not in found]
    if missing:
        raise DomainError(
            "Có giao dịch được đánh dấu không tồn tại", "flagged_transaction_not_found"
        )
    start, end = review.week_start, week_end(review.week_start)
    for i in ids:
        t = found[i]
        if not start <= t.occurred_on <= end:
            raise DomainError(
                f"Giao dịch “{t.note or t.category.name}” ngày {t.occurred_on:%d/%m/%Y} không "
                f"thuộc tuần {start:%d/%m}–{end:%d/%m/%Y}",
                "flagged_transaction_out_of_week",
            )
        if t.direction != "expense":
            raise DomainError(
                "Chỉ đánh dấu được khoản chi là “không đáng tiền”",
                "flagged_transaction_not_expense",
            )
    return ids


def add_weekly_reflection(
    db: Session, review_id: uuid.UUID, data: ReflectionCreate
) -> ReflectionAnswer:
    """Lưu câu trả lời phản tư (câu hỏi lấy từ narrative) và chuyển review sang `completed`."""
    review = get_weekly(db, review_id)
    if not data.answer and not data.flagged_transaction_ids:
        raise DomainError(
            "Bạn nhập câu trả lời hoặc chọn ít nhất một giao dịch nhé", "reflection_empty"
        )
    flagged = _validate_flagged(db, review, data.flagged_transaction_ids)
    answer = ReflectionAnswer(
        review_kind=WEEKLY,
        review_id=review.id,
        question=review.narrative.get("reflection_question") or "",
        answer=data.answer,
        flagged_transaction_ids=flagged,
    )
    review_repository.add(db, answer)
    review.status = "completed"
    db.commit()
    db.refresh(answer)
    return answer


def to_read(db: Session, review: WeeklyReview) -> WeeklyReviewRead:
    return to_reads(db, [review])[0]


def to_reads(db: Session, reviews: list[WeeklyReview]) -> list[WeeklyReviewRead]:
    reflections = review_repository.list_reflections(db, WEEKLY, [r.id for r in reviews])
    by_review: dict[uuid.UUID, list[ReflectionAnswerRead]] = {}
    for answer in reflections:
        by_review.setdefault(answer.review_id, []).append(
            ReflectionAnswerRead.model_validate(answer)
        )
    return [
        WeeklyReviewRead(
            id=r.id,
            week_start=r.week_start,
            week_end=week_end(r.week_start),
            metrics=ReviewMetrics.model_validate(r.metrics),
            narrative=ReviewNarrative.model_validate(r.narrative),
            model=r.model,
            status=r.status,  # type: ignore[arg-type]
            reflections=by_review.get(r.id, []),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reviews
    ]


def pending_weekly(db: Session, today: date) -> PendingWeeklyReviewRead:
    """Banner Thứ Hai: tuần trước có giao dịch mà review chưa có / chưa completed.
    Chỉ gợi ý — không tự tạo review."""
    previous_start = week_range(today)[0] - timedelta(days=7)
    review = review_repository.get_weekly_by_week(db, previous_start)
    has_activity = bool(
        transaction_repository.totals_by_direction(db, previous_start, week_end(previous_start))
    )
    return PendingWeeklyReviewRead(
        has_pending=today.weekday() == 0
        and has_activity
        and (review is None or review.status != "completed"),
        week_start=previous_start,
        review_id=review.id if review else None,
        review_status=review.status if review else None,  # type: ignore[arg-type]
    )
