import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession


def get_session(db: Session, session_id: uuid.UUID) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def list_sessions(db: Session, limit: int) -> list[ChatSession]:
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id.is_(None))
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def last_messages(db: Session, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, ChatMessage]:
    """Message mới nhất của từng session."""
    if not session_ids:
        return {}
    ranked = (
        select(
            ChatMessage.id,
            func.row_number()
            .over(partition_by=ChatMessage.session_id, order_by=ChatMessage.created_at.desc())
            .label("rn"),
        )
        .where(ChatMessage.session_id.in_(session_ids))
        .subquery()
    )
    stmt = select(ChatMessage).join(ranked, ranked.c.id == ChatMessage.id).where(ranked.c.rn == 1)
    return {m.session_id: m for m in db.scalars(stmt)}


def message_counts(db: Session, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not session_ids:
        return {}
    stmt = (
        select(ChatMessage.session_id, func.count())
        .where(ChatMessage.session_id.in_(session_ids))
        .group_by(ChatMessage.session_id)
    )
    return {sid: int(n) for sid, n in db.execute(stmt)}


def list_messages(db: Session, session_id: uuid.UUID) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return list(db.scalars(stmt))


def recent_messages(
    db: Session, session_id: uuid.UUID, limit: int, *, exclude_id: uuid.UUID | None = None
) -> list[ChatMessage]:
    """`limit` message gần nhất (cũ nhất trước)."""
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
    if exclude_id is not None:
        stmt = stmt.where(ChatMessage.id != exclude_id)
    stmt = stmt.order_by(ChatMessage.created_at.desc()).limit(limit)
    return list(reversed(list(db.scalars(stmt))))


def add(db: Session, entity: ChatSession | ChatMessage) -> None:
    db.add(entity)
    db.flush()


def delete(db: Session, entity: ChatSession) -> None:
    db.delete(entity)
