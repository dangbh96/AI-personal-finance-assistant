"""Lưu / đọc Weekly (Phase 6), Monthly review (Phase 7) và reflection — deterministic, không gọi AI.

Việc tạo narrative (LangGraph + OpenAI) nằm ở `agents/review_graph`; service này chỉ lưu kết quả đã
qua kiểm tra, quản lý trạng thái `generated → completed` và validate reflection.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import MonthlyReview, ReflectionAnswer, WeeklyReview
from app.repositories import review_repository, transaction_repository
from app.schemas.review import (
    MAX_DIGEST_ANSWER_LENGTH,
    FlaggedTransaction,
    MonthlyReviewMetrics,
    MonthlyReviewRead,
    PendingWeeklyReviewRead,
    ReflectionAnswerRead,
    ReflectionCreate,
    ReviewMetrics,
    ReviewNarrative,
    WeeklyReflectionDigest,
    WeeklyReviewRead,
)
from app.services.money import month_range, week_range

WEEKLY = "weekly"
MONTHLY = "monthly"


def week_end(week_start: date) -> date:
    return week_start + timedelta(days=6)


def month_end(month: date) -> date:
    return month_range(month)[1]


def ensure_week_started(week_start: date, today: date) -> None:
    if week_start.weekday() != 0:
        raise DomainError("Tuần phải bắt đầu vào Thứ Hai", "week_start_not_monday")
    if week_start > today:
        raise DomainError("Tuần này chưa bắt đầu — chưa thể tạo review", "week_not_started")


def ensure_month_started(month: date, today: date) -> None:
    if month.day != 1:
        raise DomainError("Tháng phải bắt đầu từ ngày 1", "month_not_first_day")
    if month > today:
        raise DomainError("Tháng này chưa bắt đầu — chưa thể tạo review", "month_not_started")


def _check_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")


# ---------- weekly ----------


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
    _check_range(date_from, date_to)
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
    _apply(review, metrics, narrative, model)
    db.commit()
    db.refresh(review)
    return review


# ---------- monthly ----------


def get_monthly_by_month(db: Session, month: date) -> MonthlyReview | None:
    return review_repository.get_monthly_by_month(db, month)


def get_monthly_by_month_or_404(db: Session, month: date) -> MonthlyReview:
    review = review_repository.get_monthly_by_month(db, month)
    if review is None:
        raise NotFoundError(f"Chưa có review cho tháng {month:%m/%Y}", "monthly_review_not_found")
    return review


def get_monthly(db: Session, review_id: uuid.UUID) -> MonthlyReview:
    review = review_repository.get_monthly(db, review_id)
    if review is None:
        raise NotFoundError("Không tìm thấy review tháng", "monthly_review_not_found")
    return review


def list_monthly(
    db: Session, date_from: date | None = None, date_to: date | None = None
) -> list[MonthlyReview]:
    _check_range(date_from, date_to)
    return review_repository.list_monthly(db, date_from, date_to)


def save_monthly_review(
    db: Session,
    month: date,
    metrics: ReviewMetrics,
    narrative: ReviewNarrative,
    model: str | None,
) -> MonthlyReview:
    """Như `save_weekly_review` cho tháng (`metrics` phải là `MonthlyReviewMetrics`)."""
    if not isinstance(metrics, MonthlyReviewMetrics):
        raise TypeError("Review tháng cần MonthlyReviewMetrics")
    review = review_repository.get_monthly_by_month(db, month)
    if review is None:
        review = MonthlyReview(month=month)
        db.add(review)
    _apply(review, metrics, narrative, model)
    db.commit()
    db.refresh(review)
    return review


def _apply(
    review: WeeklyReview | MonthlyReview,
    metrics: ReviewMetrics,
    narrative: ReviewNarrative,
    model: str | None,
) -> None:
    review.metrics = metrics.model_dump(mode="json")
    review.narrative = narrative.model_dump(mode="json")
    review.model = model
    review.status = "generated"


def weekly_reflections_in_month(db: Session, month: date) -> list[WeeklyReflectionDigest]:
    """Phản tư của các review tuần có Thứ Hai trong tháng (tuần cũ nhất trước). Giao dịch được
    đánh dấu nhưng đã xoá thì bỏ qua; câu trả lời dài bị cắt còn `MAX_DIGEST_ANSWER_LENGTH`."""
    start, end = month_range(month)
    reviews = sorted(review_repository.list_weekly(db, start, end), key=lambda r: r.week_start)
    answers = review_repository.list_reflections(db, WEEKLY, [r.id for r in reviews])
    if not answers:
        return []
    flagged_ids = {i for a in answers for i in a.flagged_transaction_ids}
    transactions = {t.id: t for t in transaction_repository.get_many(db, flagged_ids)}
    week_of = {r.id: r.week_start for r in reviews}
    answers.sort(key=lambda a: (week_of[a.review_id], a.created_at, a.id))
    return [
        WeeklyReflectionDigest(
            reflection_id=a.id,
            weekly_review_id=a.review_id,
            week_start=week_of[a.review_id],
            question=a.question,
            answer=_truncate(a.answer, MAX_DIGEST_ANSWER_LENGTH),
            flagged=[
                FlaggedTransaction(
                    id=t.id,
                    occurred_on=t.occurred_on,
                    note=t.note,
                    amount=t.amount,
                    category_name=t.category.name,
                    spending_type=t.spending_type,  # type: ignore[arg-type]
                )
                for i in a.flagged_transaction_ids
                if (t := transactions.get(i)) is not None
            ],
        )
        for a in answers
    ]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------- reflection ----------


def _validate_flagged(
    db: Session, ids: list[uuid.UUID], start: date, end: date, period: str
) -> list[uuid.UUID]:
    ids = list(dict.fromkeys(ids))
    found = {t.id: t for t in transaction_repository.get_many(db, ids)}
    missing = [i for i in ids if i not in found]
    if missing:
        raise DomainError(
            "Có giao dịch được đánh dấu không tồn tại", "flagged_transaction_not_found"
        )
    label = f"tuần {start:%d/%m}–{end:%d/%m/%Y}" if period == WEEKLY else f"tháng {start:%m/%Y}"
    code = (
        "flagged_transaction_out_of_week"
        if period == WEEKLY
        else ("flagged_transaction_out_of_month")
    )
    for i in ids:
        t = found[i]
        if not start <= t.occurred_on <= end:
            raise DomainError(
                f"Giao dịch “{t.note or t.category.name}” ngày {t.occurred_on:%d/%m/%Y} không "
                f"thuộc {label}",
                code,
            )
        if t.direction != "expense":
            raise DomainError("Chỉ đánh dấu được khoản chi", "flagged_transaction_not_expense")
    return ids


def _add_reflection(
    db: Session,
    review: WeeklyReview | MonthlyReview,
    kind: str,
    start: date,
    end: date,
    data: ReflectionCreate,
) -> ReflectionAnswer:
    if not data.answer and not data.flagged_transaction_ids:
        raise DomainError(
            "Bạn nhập câu trả lời hoặc chọn ít nhất một giao dịch nhé", "reflection_empty"
        )
    flagged = _validate_flagged(db, data.flagged_transaction_ids, start, end, kind)
    answer = ReflectionAnswer(
        review_kind=kind,
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


def add_weekly_reflection(
    db: Session, review_id: uuid.UUID, data: ReflectionCreate
) -> ReflectionAnswer:
    """Lưu câu trả lời phản tư (câu hỏi lấy từ narrative) + khoản chi “không đáng tiền” trong
    tuần; review chuyển sang `completed`."""
    review = get_weekly(db, review_id)
    return _add_reflection(db, review, WEEKLY, review.week_start, week_end(review.week_start), data)


def add_monthly_reflection(
    db: Session, review_id: uuid.UUID, data: ReflectionCreate
) -> ReflectionAnswer:
    """Như `add_weekly_reflection`; giao dịch đánh dấu phải là khoản chi trong tháng."""
    review = get_monthly(db, review_id)
    return _add_reflection(db, review, MONTHLY, review.month, month_end(review.month), data)


def _reflections_by_review(
    db: Session, kind: str, review_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ReflectionAnswerRead]]:
    by_review: dict[uuid.UUID, list[ReflectionAnswerRead]] = {}
    for answer in review_repository.list_reflections(db, kind, review_ids):
        by_review.setdefault(answer.review_id, []).append(
            ReflectionAnswerRead.model_validate(answer)
        )
    return by_review


# ---------- read models ----------


def to_read(db: Session, review: WeeklyReview) -> WeeklyReviewRead:
    return to_reads(db, [review])[0]


def to_reads(db: Session, reviews: list[WeeklyReview]) -> list[WeeklyReviewRead]:
    by_review = _reflections_by_review(db, WEEKLY, [r.id for r in reviews])
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


def to_monthly_read(db: Session, review: MonthlyReview) -> MonthlyReviewRead:
    return to_monthly_reads(db, [review])[0]


def to_monthly_reads(db: Session, reviews: list[MonthlyReview]) -> list[MonthlyReviewRead]:
    by_review = _reflections_by_review(db, MONTHLY, [r.id for r in reviews])
    return [
        MonthlyReviewRead(
            id=r.id,
            month=r.month,
            month_end=month_end(r.month),
            metrics=MonthlyReviewMetrics.model_validate(r.metrics),
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
