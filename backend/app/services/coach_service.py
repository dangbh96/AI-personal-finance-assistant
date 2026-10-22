"""Hội thoại Financial Coach (Phase 10): lưu session / message, gọi runner, chuẩn hoá response.

Không import `ai` / `agents` (quy tắc phụ thuộc): router truyền `runner` (một lượt `coach_graph`)
vào `send_message`. User message được commit **trước** khi chạy runner nên vẫn còn khi AI lỗi
(router trả 503); assistant message lưu kèm tool trace, evidence và metadata (model, token, chi
phí ước tính, latency, guard). Coach không ghi dữ liệu nghiệp vụ nào.
"""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ChatMessage, ChatSession
from app.repositories import chat_repository
from app.schemas.coach import (
    ChatMessageMetadata,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionRead,
    ChatSessionSummary,
    ChatSessionUpdate,
    ChatTurn,
    CitationItem,
    CoachAnswer,
    CoachMessageCreate,
    CoachMessageResponse,
    EvidenceItem,
    ToolTraceItem,
)
from app.services import coach_guard

DEFAULT_TITLE = "Cuộc trò chuyện mới"
HISTORY_MESSAGES = 10
PREVIEW_LENGTH = 120

CoachRunner = Callable[[list[ChatTurn], str], CoachAnswer]


_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _now() -> datetime:
    return datetime.now(UTC)


def _preview(text: str) -> str:
    flat = " ".join(_LINK_RE.sub(r"\1", text).replace("*", "").split())
    return flat if len(flat) <= PREVIEW_LENGTH else flat[: PREVIEW_LENGTH - 1].rstrip() + "…"


def session_read(session: ChatSession) -> ChatSessionRead:
    return ChatSessionRead(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def message_read(message: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=message.id,
        session_id=message.session_id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        tool_calls=[ToolTraceItem.model_validate(t) for t in message.tool_calls]
        if message.tool_calls is not None
        else None,
        evidence=[EvidenceItem.model_validate(e) for e in message.evidence]
        if message.evidence is not None
        else None,
        citations=[CitationItem.model_validate(c) for c in message.citations]
        if message.citations is not None
        else None,
        metadata=ChatMessageMetadata.model_validate(message.meta) if message.meta else None,
        created_at=message.created_at,
    )


# ---------- sessions ----------


def get_session(db: Session, session_id: uuid.UUID) -> ChatSession:
    session = chat_repository.get_session(db, session_id)
    if session is None:
        raise NotFoundError("Không tìm thấy cuộc trò chuyện", "chat_session_not_found")
    return session


def list_sessions(db: Session, limit: int = 20) -> list[ChatSessionSummary]:
    sessions = chat_repository.list_sessions(db, limit)
    ids = [s.id for s in sessions]
    last = chat_repository.last_messages(db, ids)
    counts = chat_repository.message_counts(db, ids)
    return [
        ChatSessionSummary(
            **session_read(s).model_dump(),
            last_message_preview=_preview(last[s.id].content) if s.id in last else None,
            message_count=counts.get(s.id, 0),
        )
        for s in sessions
    ]


def create_session(db: Session, data: ChatSessionCreate) -> ChatSession:
    session = ChatSession(title=data.title or DEFAULT_TITLE)
    chat_repository.add(db, session)
    db.commit()
    return session


def get_session_detail(db: Session, session_id: uuid.UUID) -> ChatSessionDetail:
    session = get_session(db, session_id)
    return ChatSessionDetail(
        **session_read(session).model_dump(),
        messages=[message_read(m) for m in chat_repository.list_messages(db, session.id)],
    )


def rename_session(db: Session, session_id: uuid.UUID, data: ChatSessionUpdate) -> ChatSession:
    session = get_session(db, session_id)
    session.title = data.title
    db.commit()
    return session


def delete_session(db: Session, session_id: uuid.UUID) -> None:
    chat_repository.delete(db, get_session(db, session_id))
    db.commit()


# ---------- messages ----------


def _touch(session: ChatSession) -> None:
    session.updated_at = _now()


def add_user_message(db: Session, session: ChatSession, content: str) -> ChatMessage:
    message = ChatMessage(session_id=session.id, role="user", content=content, created_at=_now())
    chat_repository.add(db, message)
    if session.title == DEFAULT_TITLE:
        session.title = coach_guard.make_title(content)
    _touch(session)
    db.commit()
    return message


def add_assistant_message(db: Session, session: ChatSession, answer: CoachAnswer) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer.content,
        tool_calls=[t.model_dump(mode="json") for t in answer.tool_trace],
        evidence=[e.model_dump(mode="json") for e in answer.evidence],
        citations=[c.model_dump(mode="json") for c in answer.citations],
        meta=answer.metadata.model_dump(mode="json"),
        created_at=_now(),
    )
    chat_repository.add(db, message)
    _touch(session)
    db.commit()
    return message


def history(db: Session, session: ChatSession, *, exclude_id: uuid.UUID) -> list[ChatTurn]:
    """Các lượt user / assistant gần nhất (không gồm message vừa gửi) làm ngữ cảnh."""
    return [
        ChatTurn(role=m.role, content=m.content)  # type: ignore[arg-type]
        for m in chat_repository.recent_messages(
            db, session.id, HISTORY_MESSAGES, exclude_id=exclude_id
        )
        if m.role in ("user", "assistant")
    ]


def send_message(
    db: Session, session_id: uuid.UUID, data: CoachMessageCreate, runner: CoachRunner
) -> CoachMessageResponse:
    """Lưu câu hỏi → chạy `runner` (có thể raise `AIUnavailable`) → lưu câu trả lời."""
    session = get_session(db, session_id)
    user_message = add_user_message(db, session, data.content)
    turns = history(db, session, exclude_id=user_message.id)
    answer = runner(turns, data.content)
    assistant_message = add_assistant_message(db, session, answer)
    return CoachMessageResponse(
        session=session_read(session),
        user_message=message_read(user_message),
        assistant_message=message_read(assistant_message),
        tool_trace=answer.tool_trace,
        evidence=answer.evidence,
        citations=answer.citations,
        guard_status=answer.metadata.guard_status,
    )
