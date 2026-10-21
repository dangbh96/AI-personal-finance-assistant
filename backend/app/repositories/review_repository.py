import uuid
from collections.abc import Collection
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReflectionAnswer, WeeklyReview


def get_weekly(db: Session, review_id: uuid.UUID) -> WeeklyReview | None:
    return db.get(WeeklyReview, review_id)


def get_weekly_by_week(db: Session, week_start: date) -> WeeklyReview | None:
    return db.scalar(select(WeeklyReview).where(WeeklyReview.week_start == week_start))


def list_weekly(
    db: Session, date_from: date | None = None, date_to: date | None = None
) -> list[WeeklyReview]:
    stmt = select(WeeklyReview).order_by(WeeklyReview.week_start.desc())
    if date_from is not None:
        stmt = stmt.where(WeeklyReview.week_start >= date_from)
    if date_to is not None:
        stmt = stmt.where(WeeklyReview.week_start <= date_to)
    return list(db.scalars(stmt))


def add(db: Session, entity: WeeklyReview | ReflectionAnswer) -> None:
    db.add(entity)
    db.flush()


def list_reflections(
    db: Session, review_kind: str, review_ids: Collection[uuid.UUID]
) -> list[ReflectionAnswer]:
    if not review_ids:
        return []
    stmt = (
        select(ReflectionAnswer)
        .where(ReflectionAnswer.review_kind == review_kind)
        .where(ReflectionAnswer.review_id.in_(review_ids))
        .order_by(ReflectionAnswer.created_at, ReflectionAnswer.id)
    )
    return list(db.scalars(stmt))
