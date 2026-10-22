import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.ai import embeddings
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.knowledge import (
    MAX_KNOWLEDGE_LIMIT,
    MAX_KNOWLEDGE_QUERY_LENGTH,
    KnowledgeChunkRead,
    KnowledgeDocumentList,
    KnowledgeReindexRequest,
    KnowledgeReindexResult,
    KnowledgeSearchResponse,
)
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

AI_ERRORS = {
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse, "description": "Dịch vụ embedding trả kết quả không hợp lệ"},
    503: {"model": ErrorResponse, "description": "AI chưa cấu hình / không khả dụng"},
}


@router.get("/search", response_model=KnowledgeSearchResponse, responses=AI_ERRORS)
def search_knowledge(
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=MAX_KNOWLEDGE_QUERY_LENGTH)],
    limit: Annotated[int, Query(ge=1, le=MAX_KNOWLEDGE_LIMIT)] = 5,
):
    """(Dev / debug) Tìm đoạn kiến thức liên quan nhất (pgvector cosine). Chỉ đọc."""
    return knowledge_service.search(db, q, embeddings.embed_queries, limit=limit)


@router.get("/documents", response_model=KnowledgeDocumentList)
def list_documents(db: DbSession):
    """Tài liệu đã ingest + số đoạn."""
    return knowledge_service.list_documents(db)


@router.get(
    "/chunks/{chunk_id}",
    response_model=KnowledgeChunkRead,
    responses={404: {"model": ErrorResponse}},
)
def get_chunk(db: DbSession, chunk_id: uuid.UUID):
    """Toàn văn một đoạn — để mở trích dẫn của Coach."""
    return knowledge_service.get_chunk(db, chunk_id)


@router.post("/reindex", response_model=KnowledgeReindexResult, responses=AI_ERRORS)
def reindex(db: DbSession, data: KnowledgeReindexRequest | None = None):
    """(Dev) Ingest lại thư mục kiến thức (mặc định `backend/knowledge`) — như
    `python -m app.scripts.ingest_knowledge knowledge/`. Chỉ nhận đường dẫn trong `backend/`."""
    data = data or KnowledgeReindexRequest()
    path = knowledge_service.resolve_ingest_path(data.path)
    report = knowledge_service.ingest_path(db, path, embeddings.embed_knowledge, prune=data.prune)
    return KnowledgeReindexResult(**report.__dict__)
