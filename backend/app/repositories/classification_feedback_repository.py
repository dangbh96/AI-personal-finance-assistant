import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClassificationFeedback


def add(db: Session, feedback: ClassificationFeedback) -> ClassificationFeedback:
    db.add(feedback)
    db.flush()
    return feedback


def list_for_transaction(db: Session, transaction_id: uuid.UUID) -> list[ClassificationFeedback]:
    return list(
        db.scalars(
            select(ClassificationFeedback)
            .where(ClassificationFeedback.transaction_id == transaction_id)
            .order_by(ClassificationFeedback.created_at)
        )
    )
