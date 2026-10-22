"""Semantic search giao dịch (Phase 15)."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Direction, SpendingType, TransactionSource

MatchReason = Literal["semantic", "keyword", "hybrid"]

MAX_QUERY_LENGTH = 200
MAX_SEARCH_LIMIT = 50


class TransactionSearchResult(BaseModel):
    transaction_id: uuid.UUID
    occurred_on: date
    note: str | None
    amount: int
    direction: Direction
    category_id: uuid.UUID
    category_name: str
    category_icon: str | None
    spending_type: SpendingType | None
    source: TransactionSource
    score: float = Field(description="0.75 × độ tương đồng ngữ nghĩa + 0.25 × điểm từ khoá (0–1)")
    semantic_score: float | None = Field(
        description="1 − cosine distance; null nếu giao dịch chưa có embedding"
    )
    keyword_boost: float = Field(description="1 = ghi chú chứa từ khoá, 0.5 = tên danh mục chứa…")
    match_reason: MatchReason


class TransactionSearchResponse(BaseModel):
    query: str
    from_date: date | None
    to_date: date | None
    limit: int
    result_count: int
    total_amount: int = Field(description="Tổng chi (expense) của các kết quả")
    income_total: int
    expense_total: int
    net: int = Field(description="income_total − expense_total")
    missing_embedding_count: int = Field(
        description="Giao dịch trong khoảng ngày chưa có embedding (chỉ tìm được theo từ khoá)"
    )
    results: list[TransactionSearchResult]


class ReindexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_ids: list[uuid.UUID] | None = Field(
        default=None,
        max_length=1000,
        description="Chỉ embed lại các giao dịch này; bỏ trống = mọi giao dịch thiếu / cũ",
    )
    limit: int = Field(default=500, ge=1, le=5000)


class ReindexResult(BaseModel):
    processed_count: int = Field(description="Số giao dịch vừa được (tạo lại) embedding")
    unchanged_count: int = Field(description="Đã có embedding khớp nội dung, bỏ qua")
    remaining_count: int = Field(description="Còn thiếu / cũ sau lần chạy này")
