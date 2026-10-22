from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.ai import embeddings
from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.search import (
    MAX_QUERY_LENGTH,
    MAX_SEARCH_LIMIT,
    ReindexRequest,
    ReindexResult,
    TransactionSearchResponse,
)
from app.services import embedding_service, search_service

router = APIRouter(prefix="/search", tags=["search"])

AI_ERRORS = {
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse, "description": "Dịch vụ embedding trả kết quả không hợp lệ"},
    503: {"model": ErrorResponse, "description": "AI chưa cấu hình / không khả dụng"},
}


@router.get("/transactions", response_model=TransactionSearchResponse, responses=AI_ERRORS)
def search_transactions(
    db: DbSession,
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=MAX_QUERY_LENGTH,
            description="Nội dung cần tìm, vd 'ăn ngoài', 'đi lại', 'Highlands'",
        ),
    ],
    date_from: Annotated[date | None, Query(alias="from", description="Từ ngày (bao gồm)")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="Đến ngày (bao gồm)")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = 20,
):
    """Tìm giao dịch theo ý nghĩa (embedding + pgvector cosine) kết hợp từ khoá (ILIKE). Chỉ
    đọc. Thiếu `OPENAI_API_KEY` / AI lỗi → 503 (không tìm được ngữ nghĩa)."""
    return search_service.search_transactions(
        db, q, embeddings.embed_queries, date_from=date_from, date_to=date_to, limit=limit
    )


@router.post("/transactions/reindex", response_model=ReindexResult, responses=AI_ERRORS)
def reindex_transactions(db: DbSession, data: ReindexRequest | None = None):
    """(Dev) Tạo / cập nhật embedding cho giao dịch thiếu hoặc đã cũ — như
    `python -m app.scripts.backfill_embeddings` nhưng qua API, tối đa `limit` giao dịch."""
    data = data or ReindexRequest()
    report = embedding_service.backfill(
        db,
        embeddings.embed_documents,
        limit=data.limit,
        transaction_ids=data.transaction_ids,
        force=data.transaction_ids is not None,
    )
    return ReindexResult(
        processed_count=report.processed,
        unchanged_count=report.unchanged,
        remaining_count=report.remaining_missing,
    )
