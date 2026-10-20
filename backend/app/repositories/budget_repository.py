import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget


def get(db: Session, budget_id: uuid.UUID) -> Budget | None:
    return db.get(Budget, budget_id)


def get_by_month(db: Session, period_month: date) -> Budget | None:
    return db.scalar(
        select(Budget).where(Budget.user_id.is_(None), Budget.period_month == period_month)
    )


def list_budgets(
    db: Session, *, date_from: date | None = None, date_to: date | None = None
) -> list[Budget]:
    """Tháng mới nhất trước."""
    stmt = select(Budget).where(Budget.user_id.is_(None))
    if date_from is not None:
        stmt = stmt.where(Budget.period_month >= date_from)
    if date_to is not None:
        stmt = stmt.where(Budget.period_month <= date_to)
    return list(db.scalars(stmt.order_by(Budget.period_month.desc())))


def add(db: Session, budget: Budget) -> Budget:
    db.add(budget)
    db.flush()
    return budget


def delete(db: Session, budget: Budget) -> None:
    db.delete(budget)
    db.flush()
