import uuid
from collections.abc import Collection
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import RecurringTransaction, Transaction


def get(db: Session, recurring_id: uuid.UUID) -> RecurringTransaction | None:
    return db.get(RecurringTransaction, recurring_id)


def list_recurring(db: Session, *, active: bool | None = None) -> list[RecurringTransaction]:
    """Đang bật trước; trong nhóm theo `next_due_on`, tên."""
    stmt = select(RecurringTransaction).where(RecurringTransaction.user_id.is_(None))
    if active is not None:
        stmt = stmt.where(RecurringTransaction.active.is_(active))
    stmt = stmt.order_by(
        RecurringTransaction.active.desc(),
        RecurringTransaction.next_due_on,
        RecurringTransaction.name,
        RecurringTransaction.id,
    )
    return list(db.scalars(stmt))


def add(db: Session, recurring: RecurringTransaction) -> RecurringTransaction:
    db.add(recurring)
    db.flush()
    return recurring


def transaction_counts(db: Session, recurring_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not recurring_ids:
        return {}
    rows = db.execute(
        select(Transaction.recurring_id, func.count())
        .where(Transaction.recurring_id.in_(list(recurring_ids)))
        .group_by(Transaction.recurring_id)
    )
    return {rid: int(n) for rid, n in rows}


def link_transactions(
    db: Session, transaction_ids: Collection[uuid.UUID], recurring_id: uuid.UUID
) -> int:
    """Gắn giao dịch (chưa thuộc khoản định kỳ nào) vào khoản định kỳ vừa xác nhận."""
    if not transaction_ids:
        return 0
    result = db.execute(
        update(Transaction)
        .where(Transaction.id.in_(list(transaction_ids)), Transaction.recurring_id.is_(None))
        .values(recurring_id=recurring_id)
    )
    db.flush()
    return result.rowcount or 0


def linked_transactions_between(db: Session, date_from: date, date_to: date) -> list[Transaction]:
    """Giao dịch đã gắn khoản định kỳ trong kỳ (cũ nhất trước)."""
    stmt = (
        select(Transaction)
        .where(
            Transaction.recurring_id.is_not(None),
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
        )
        .order_by(Transaction.occurred_on, Transaction.created_at, Transaction.id)
    )
    return list(db.scalars(stmt))


def unlinked_transactions_between(db: Session, date_from: date, date_to: date) -> list[Transaction]:
    """Giao dịch chưa gắn khoản định kỳ trong kỳ (đầu vào phát hiện định kỳ)."""
    stmt = (
        select(Transaction)
        .where(
            Transaction.recurring_id.is_(None),
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
        )
        .order_by(Transaction.occurred_on, Transaction.created_at, Transaction.id)
    )
    return list(db.scalars(stmt))


def earliest_transaction_date(db: Session) -> date | None:
    return db.scalar(select(func.min(Transaction.occurred_on)))
