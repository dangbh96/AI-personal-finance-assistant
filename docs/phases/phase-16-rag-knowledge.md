# Phase 16 — RAG Personal Finance Knowledge Base

| | |
|---|---|
| **ID** | `phase-16-rag-knowledge` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 10, 15 phải Done |
| **Mở khoá** | Phase 18 |
| **Milestone** | **M6 — Full AI curriculum** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 10 và Phase 15
2. [vision.md](../product/vision.md) — AI đưa evidence, không quyết định thay user
3. [glossary.md](../product/glossary.md) — Coach, Observation/Explanation/Action
4. [data-model.md](../architecture/data-model.md) — `KNOWLEDGE_DOCUMENT`, `KNOWLEDGE_CHUNK`
5. [backend-components.md](../architecture/backend-components.md) — Coach graph + tools bọc services
6. [ai-architecture.md](../architecture/ai-architecture.md) — `search_knowledge`, citations, guardrails
7. [frontend-structure.md](../architecture/frontend-structure.md) — `/coach` hiển thị nguồn trích dẫn
8. ADR [002](../architecture/decisions/ADR-002-postgres-pgvector.md), [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md)

Trạng thái code giả định: Phase 10 đã có Coach LangGraph với tool-calling; Phase 15 đã bật pgvector và có embedding service/backfill pattern.

## 2. Mục tiêu & giá trị cho user

Coach trả lời câu hỏi kiến thức tài chính cá nhân bằng nội dung có nguồn trích dẫn, đồng thời biết kết hợp dữ liệu thật của user. Ví dụ "50/30/20 là gì, có phù hợp với tao không?" phải vừa giải thích quy tắc, vừa so với breakdown chi tiêu thực tế.

## 3. Scope

**In scope**
- Bảng `knowledge_documents`, `knowledge_chunks` có embedding `vector(1536)`.
- Script ingest `python -m app.scripts.ingest_knowledge docs_kb/` đọc markdown và PDF bằng `pypdf`.
- Chunking khoảng 500–800 tokens, overlap 100 tokens, lưu source/title/heading metadata.
- Bộ knowledge base tự viết trong `backend/knowledge/` (không copy tài liệu có bản quyền): 50/30/20, envelope/jars, pay yourself first, emergency fund, sinking funds, debt basics.
- Coach tool `search_knowledge` trả chunks + citations.
- Answer format có mục `Nguồn:` và citation theo title/heading/source.
- Retrieval eval hit@3.

**Out of scope**
- Crawl web tự động.
- Tư vấn đầu tư, thuế, bảo hiểm phức tạp.
- Citation theo chuẩn học thuật đầy đủ; chỉ cần nguồn nội bộ rõ ràng.
- Upload knowledge từ UI.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`knowledge_documents`: `id`, `title`, `source`, `source_type` (`markdown|pdf`), `content_hash UNIQUE`, `metadata JSONB`, timestamps.

`knowledge_chunks`: `id`, `document_id FK`, `chunk_index`, `heading TEXT NULL`, `content TEXT`, `embedding vector(1536)`, `model TEXT`, `metadata JSONB`, timestamps.

Index:
- `knowledge_chunks(document_id, chunk_index)`
- HNSW cosine index trên `knowledge_chunks.embedding`
- unique `(document_id, chunk_index)`

`metadata` chứa: `{ "source_path": "...", "heading_path": ["..."], "tags": ["budgeting"], "language": "vi" }`.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/knowledge/search` | Dev/debug search knowledge | `q`, `limit=5` | `{results:[{chunk_id,title,heading,content,score,citation}]}` |
| POST | `/api/v1/knowledge/reindex` | Dev-only ingest lại thư mục mặc định | `{path?: "backend/knowledge"}` | `{documents, chunks}` |

Script chính:
```bash
cd backend
python -m app.scripts.ingest_knowledge docs_kb/
python -m app.scripts.ingest_knowledge knowledge/   # = backend/knowledge/
```

Pydantic schemas:
```python
class KnowledgeSearchResult(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    heading: str | None
    source: str
    content: str
    score: float
    citation: str

class CoachAnswerWithCitations(BaseModel):
    observation: str
    explanation: str
    action: str | None
    citations: list[str]
```

`agents/tools/search_knowledge.py` là read-only tool:
`search_knowledge(query: str, limit: int = 4) -> list[KnowledgeSearchResult]`.

### 4.3 AI

- Embedding: `OPENAI_EMBEDDING_MODEL` cho chunks và query.
- Coach model: `OPENAI_MODEL_SMART` khi trả lời cần kết hợp knowledge + personal tools; `OPENAI_MODEL_FAST` chỉ dùng cho guard/fallback nếu có.
- Prompt outline cho Coach:
  1. Xác định câu hỏi cần kiến thức chung hay dữ liệu cá nhân hay cả hai.
  2. Nếu có khái niệm tài chính → gọi `search_knowledge`.
  3. Nếu user hỏi "có phù hợp với tao không" → bắt buộc gọi personal-data tool (`get_spending_summary`, `get_budget_status` hoặc `get_category_trend`).
  4. Trả lời theo Observation → Explanation → Action, cuối có `Nguồn:`.
- Guardrails: không bịa citation; mỗi claim kiến thức phải dựa trên chunk trả về; không đưa lời khuyên pháp lý/đầu tư; nếu thiếu dữ liệu cá nhân thì nói rõ và gợi ý user tạo budget/transactions.

### 4.4 Frontend

- `/coach` mở rộng message renderer: hiển thị block `Nguồn:` dạng collapsible citations.
- Tool trace hiển thị "Đã tra kiến thức: 50/30/20" và "Đã xem breakdown chi tiêu tháng này" để user hiểu evidence.
- Nếu câu trả lời có citation, click mở snippet chunk trong drawer.

## 5. Task breakdown

- [ ] T1 Migration `knowledge_documents`, `knowledge_chunks` + HNSW index
- [ ] T2 Thêm dependency `pypdf` và module loader markdown/pdf
- [ ] T3 Implement chunker 500–800 tokens, overlap 100, giữ heading metadata
- [ ] T4 Viết knowledge base tự soạn trong `backend/knowledge/`: `50-30-20.md`, `envelope-jars.md`, `pay-yourself-first.md`, `emergency-fund.md`, `sinking-funds.md`, `debt-basics.md`
- [ ] T5 Implement ingest script idempotent theo `content_hash`
- [ ] T6 Implement `knowledge_service.search` dùng pgvector cosine + metadata citation
- [ ] T7 Add Coach tool `search_knowledge` và update Coach prompt/guard
- [ ] T8 Golden tests: citations, personal-data tool required khi hỏi "có phù hợp với tao không"
- [ ] T9 Retrieval eval hit@3 với 12 queries
- [ ] T10 UI citations trong `/coach`
- [ ] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-16: rag knowledge`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
(cd backend && alembic upgrade head && ruff check . && pytest tests/unit/test_knowledge_chunking.py tests/api/test_knowledge_search.py)
(cd backend && python -m app.scripts.ingest_knowledge knowledge/)
(cd backend && pytest -m ai tests/ai_golden/test_rag_coach.py)
(cd frontend && npm run gen:api && npm run lint && npm run dev)
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Ingest 6 markdown tự viết | Tạo 6 documents, tối thiểu 12 chunks, chạy lại không nhân đôi |
| 2 | PDF 3 trang qua `pypdf` | Extract text, chunk có source pdf |
| 3 | Query "quỹ khẩn cấp bao nhiêu tháng" | hit@3 chứa doc emergency fund |
| 4 | Query "phương pháp hũ" | hit@3 chứa envelope/jars |
| 5 | Coach: "50/30/20 là gì?" | Trả lời có `Nguồn:` trỏ tới doc 50/30/20 |
| 6 | Coach: "50/30/20 là gì, có phù hợp với tao không" | Gọi `search_knowledge` và một personal-data tool; so sánh breakdown thực tế của user |
| 7 | Knowledge chunk không chứa thông tin | Coach nói không tìm thấy nguồn đủ tin cậy, không bịa |
| 8 | Retrieval eval 12 queries | hit@3 ≥ 0.80 |

**Kịch bản thao tác UI**
1. Mở `/coach`, hỏi "Pay yourself first khác gì 50/30/20?" → thấy giải thích + nguồn.
2. Hỏi "quỹ khẩn cấp của tao nên bao nhiêu?" → Coach tra knowledge và dữ liệu chi tiêu thiết yếu.
3. Mở citation drawer → thấy title, heading, source path và snippet.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] Knowledge base là nội dung tự viết, không sao chép tài liệu có bản quyền
- [ ] Coach bắt buộc gọi personal-data tool khi user hỏi mức độ phù hợp cá nhân
- [ ] Câu trả lời kiến thức có `Nguồn:` và citation thật
- [ ] Retrieval eval hit@3 đạt ngưỡng
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền, đánh dấu M6
- [ ] Commit `phase-16: rag knowledge`

## 8. Rủi ro / câu hỏi mở

- Tokenizer chính xác có thể cần thêm dependency; nếu chưa có, dùng ước lượng theo từ và ghi rõ trong handoff.
- Câu hỏi tiếng Việt đời thường có thể cần synonyms trong golden set ("quỹ dự phòng", "tiền phòng thân").
- Không được copy nguyên văn sách/blog; chỉ viết lại bằng lời của dự án.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
