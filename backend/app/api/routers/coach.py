import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.agents import coach_graph
from app.core.db import DbSession
from app.schemas.coach import (
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionRead,
    ChatSessionUpdate,
    ChatTurn,
    CoachMessageCreate,
    CoachMessageResponse,
)
from app.schemas.common import ErrorResponse
from app.services import coach_service

router = APIRouter(prefix="/coach", tags=["coach"])

NOT_FOUND = {404: {"model": ErrorResponse}}
AI_ERRORS = {
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.get("/sessions", response_model=ChatSessionList)
def list_coach_sessions(db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    """Các cuộc trò chuyện, cập nhật gần nhất trước (kèm đoạn đầu message cuối)."""
    return ChatSessionList(items=coach_service.list_sessions(db, limit))


@router.post(
    "/sessions",
    response_model=ChatSessionRead,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
def create_coach_session(db: DbSession, data: ChatSessionCreate):
    """Tạo session; bỏ trống `title` → đặt theo câu hỏi đầu tiên."""
    return coach_service.session_read(coach_service.create_session(db, data))


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail, responses=NOT_FOUND)
def get_coach_session(db: DbSession, session_id: uuid.UUID):
    """Session + toàn bộ message (assistant kèm tool trace, evidence, metadata)."""
    return coach_service.get_session_detail(db, session_id)


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionRead,
    responses={**NOT_FOUND, 422: {"model": ErrorResponse}},
)
def rename_coach_session(db: DbSession, session_id: uuid.UUID, data: ChatSessionUpdate):
    return coach_service.session_read(coach_service.rename_session(db, session_id, data))


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND
)
def delete_coach_session(db: DbSession, session_id: uuid.UUID):
    coach_service.delete_session(db, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=CoachMessageResponse,
    responses={**NOT_FOUND, **AI_ERRORS},
)
def send_coach_message(db: DbSession, session_id: uuid.UUID, data: CoachMessageCreate):
    """Gửi câu hỏi và chạy `coach_graph` (plain JSON, không stream).

    Coach chỉ gọi tool đọc dữ liệu; không tạo / sửa giao dịch hay ngân sách. Câu hỏi ngoài phạm
    vi (đầu tư, chứng khoán, crypto, thuế) hoặc yêu cầu ghi dữ liệu → trả lời mẫu, không gọi AI.
    AI lỗi → 503 (`AI_*`), câu hỏi vẫn được lưu."""
    today = data.today or date.today()

    def runner(history: list[ChatTurn], question: str):
        return coach_graph.run_coach(db, question, today=today, history=history)

    return coach_service.send_message(db, session_id, data, runner)
