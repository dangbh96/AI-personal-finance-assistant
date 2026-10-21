import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BudgetAdvice, BudgetAllocation


def get(db: Session, advice_id: uuid.UUID) -> BudgetAdvice | None:
    return db.get(BudgetAdvice, advice_id)


def list_advice(
    db: Session,
    *,
    month: date | None = None,
    status: str | None = None,
    allocation_id: uuid.UUID | None = None,
) -> list[BudgetAdvice]:
    """Tháng mới nhất trước, trong tháng theo thứ tự dòng phân bổ, rồi advice mới nhất trước."""
    stmt = (
        select(BudgetAdvice)
        .join(BudgetAllocation, BudgetAdvice.budget_allocation_id == BudgetAllocation.id)
        .where(BudgetAdvice.user_id.is_(None))
    )
    if month is not None:
        stmt = stmt.where(BudgetAdvice.month == month)
    if status is not None:
        stmt = stmt.where(BudgetAdvice.status == status)
    if allocation_id is not None:
        stmt = stmt.where(BudgetAdvice.budget_allocation_id == allocation_id)
    stmt = stmt.order_by(
        BudgetAdvice.month.desc(), BudgetAllocation.position, BudgetAdvice.created_at.desc()
    )
    return list(db.scalars(stmt).unique())


def for_allocation_month(db: Session, allocation_id: uuid.UUID, month: date) -> list[BudgetAdvice]:
    return list(
        db.scalars(
            select(BudgetAdvice).where(
                BudgetAdvice.budget_allocation_id == allocation_id, BudgetAdvice.month == month
            )
        ).unique()
    )


def add(db: Session, advice: BudgetAdvice) -> BudgetAdvice:
    db.add(advice)
    db.flush()
    return advice
