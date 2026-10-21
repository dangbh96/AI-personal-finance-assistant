import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Receipt


def get(db: Session, receipt_id: uuid.UUID) -> Receipt | None:
    return db.get(Receipt, receipt_id)


def add(db: Session, receipt: Receipt) -> Receipt:
    db.add(receipt)
    db.flush()
    return receipt


def list_receipts(db: Session, *, status: str | None = None, limit: int = 20) -> list[Receipt]:
    """Mới nhất trước."""
    stmt = select(Receipt).where(Receipt.user_id.is_(None))
    if status is not None:
        stmt = stmt.where(Receipt.status == status)
    stmt = stmt.order_by(Receipt.created_at.desc(), Receipt.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def latest_other_with_sha256(db: Session, sha256: str, exclude_id: uuid.UUID) -> Receipt | None:
    """Receipt khác có cùng nội dung ảnh (để cảnh báo upload trùng)."""
    stmt = (
        select(Receipt)
        .where(Receipt.sha256 == sha256, Receipt.id != exclude_id)
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
        .limit(1)
    )
    return db.scalar(stmt)
