# ADR-002: PostgreSQL 16 + pgvector

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Cần DB quan hệ cho dữ liệu tài chính (tính toán chính xác, transaction) và vector store cho semantic search / RAG.

## Quyết định

Một instance **PostgreSQL 16** chạy image `pgvector/pgvector:pg16` qua Docker Compose. Vector lưu trong cùng DB (bảng `transaction_embeddings`, `knowledge_chunks`), HNSW index, cosine distance.

## Phương án đã cân nhắc

Pinecone (thêm service cloud, thêm key, dữ liệu tài chính ra ngoài); Chroma (thêm store riêng, khó join với giao dịch); SQLite (không có pgvector, khó mở rộng).

## Hệ quả

Join trực tiếp vector search với filter ngày/category bằng SQL. Cần Docker để chạy local.
