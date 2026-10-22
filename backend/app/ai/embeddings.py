"""Embedding cho semantic search (Phase 15) và RAG knowledge base (Phase 16).

Bọc `openai_client.create_embeddings` (`OPENAI_EMBEDDING_MODEL`, timeout / retry, log token) và
trả về kiểu `EmbeddedTexts` của `services/embedding_service` — services nhận hàm này qua tham số
(`embedder`) nên không import `ai`.
"""

from app.ai import openai_client
from app.services.embedding_service import EmbeddedTexts

TASK_DOCUMENTS = "embed_transactions"
TASK_QUERY = "embed_query"
TASK_KNOWLEDGE = "embed_knowledge"


def embed_documents(texts: list[str]) -> EmbeddedTexts:
    """Embed nhiều chuỗi (tự chia lô 100). Raise `AIUnavailable` nếu lỗi."""
    result = openai_client.create_embeddings(texts, task=TASK_DOCUMENTS)
    return EmbeddedTexts(vectors=result.vectors, model=result.model)


def embed_queries(texts: list[str]) -> EmbeddedTexts:
    """Embed câu tìm kiếm của user."""
    result = openai_client.create_embeddings(texts, task=TASK_QUERY)
    return EmbeddedTexts(vectors=result.vectors, model=result.model)


def embed_knowledge(texts: list[str]) -> EmbeddedTexts:
    """Embed đoạn tài liệu kiến thức khi ingest (Phase 16)."""
    result = openai_client.create_embeddings(texts, task=TASK_KNOWLEDGE)
    return EmbeddedTexts(vectors=result.vectors, model=result.model)
