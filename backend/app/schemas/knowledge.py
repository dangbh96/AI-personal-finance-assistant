"""Knowledge base / RAG (Phase 16)."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

MAX_KNOWLEDGE_QUERY_LENGTH = 300
MAX_KNOWLEDGE_LIMIT = 10


class KnowledgeSearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    heading: str | None
    source: str
    content: str
    score: float = Field(description="1 − cosine distance")
    citation: str = Field(description="“Tiêu đề — mục (đường dẫn)”")


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResult] = Field(description="Liên quan nhất trước")


class KnowledgeChunkRead(KnowledgeSearchResult):
    chunk_index: int
    headings: list[str] = Field(description="Mọi heading mục nằm trong đoạn")
    source_type: str


class KnowledgeReindexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(
        default=None,
        max_length=300,
        description="Thư mục / file trong `backend/` (mặc định `knowledge`)",
    )
    prune: bool = Field(
        default=False, description="Xoá tài liệu đã ingest từ thư mục này mà file không còn"
    )


class KnowledgeReindexResult(BaseModel):
    documents: int = Field(description="Số tài liệu trong thư mục đã xử lý")
    chunks: int = Field(description="Tổng số đoạn của các tài liệu đó")
    created: int
    updated: int
    unchanged: int
    skipped: int = Field(description="Trùng nội dung với tài liệu khác / file lỗi")
    removed: int
    errors: list[str]


class KnowledgeDocumentRead(BaseModel):
    id: uuid.UUID
    title: str
    source: str
    source_type: str
    chunk_count: int
    tags: list[str]


class KnowledgeDocumentList(BaseModel):
    items: list[KnowledgeDocumentRead]
