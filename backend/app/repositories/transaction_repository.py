import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, func, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from app.models import Category, Transaction


@dataclass(frozen=True)
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    category_id: uuid.UUID | None = None
    spending_type: str | None = None
    direction: str | None = None
    q: str | None = None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(filters: TransactionFilters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if filters.date_from is not None:
        conds.append(Transaction.occurred_on >= filters.date_from)
    if filters.date_to is not None:
        conds.append(Transaction.occurred_on <= filters.date_to)
    if filters.category_id is not None:
        conds.append(Transaction.category_id == filters.category_id)
    if filters.spending_type is not None:
        conds.append(Transaction.spending_type == filters.spending_type)
    if filters.direction is not None:
        conds.append(Transaction.direction == filters.direction)
    if filters.q:
        conds.append(Transaction.note.ilike(f"%{_escape_like(filters.q)}%", escape="\\"))
    return conds


def get(db: Session, transaction_id: uuid.UUID) -> Transaction | None:
    return db.get(Transaction, transaction_id)


def list_transactions(
    db: Session, filters: TransactionFilters, *, offset: int, limit: int
) -> tuple[list[Transaction], int]:
    conds = _conditions(filters)
    total = db.scalar(select(func.count()).select_from(Transaction).where(*conds)) or 0
    stmt = (
        select(Transaction)
        .where(*conds)
        .order_by(
            Transaction.occurred_on.desc(), Transaction.created_at.desc(), Transaction.id.desc()
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt)), total


def totals_by_direction_and_spending_type(
    db: Session, filters: TransactionFilters
) -> list[tuple[str, str | None, int]]:
    stmt = (
        select(Transaction.direction, Transaction.spending_type, func.sum(Transaction.amount))
        .where(*_conditions(filters))
        .group_by(Transaction.direction, Transaction.spending_type)
    )
    return [(direction, st, int(total)) for direction, st, total in db.execute(stmt)]


def totals_by_category(
    db: Session, filters: TransactionFilters
) -> list[tuple[uuid.UUID, str, str, str | None, int]]:
    total = func.sum(Transaction.amount)
    stmt = (
        select(Category.id, Category.name, Category.kind, Category.icon, total)
        .join(Transaction, Transaction.category_id == Category.id)
        .where(*_conditions(filters))
        .group_by(Category.id)
        .order_by(total.desc(), Category.name)
    )
    return [(cid, name, kind, icon, int(t)) for cid, name, kind, icon, t in db.execute(stmt)]


def add(db: Session, transaction: Transaction) -> Transaction:
    db.add(transaction)
    db.flush()
    return transaction


def delete(db: Session, transaction: Transaction) -> None:
    db.delete(transaction)
    db.flush()


def delete_in_range(db: Session, date_from: date, date_to: date) -> int:
    result = db.execute(
        sa_delete(Transaction).where(
            Transaction.occurred_on >= date_from, Transaction.occurred_on <= date_to
        )
    )
    return result.rowcount or 0
