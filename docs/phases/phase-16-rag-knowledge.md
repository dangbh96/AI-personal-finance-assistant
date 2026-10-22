# Phase 16 — RAG Personal Finance Knowledge Base

| | |
|---|---|
| **ID** | `phase-16-rag-knowledge` |
| **Trạng thái** | Done |
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

- [x] T1 Migration `knowledge_documents`, `knowledge_chunks` + HNSW index
- [x] T2 Thêm dependency `pypdf` và module loader markdown/pdf
- [x] T3 Implement chunker 500–800 tokens, overlap 100, giữ heading metadata
- [x] T4 Viết knowledge base tự soạn trong `backend/knowledge/`: `50-30-20.md`, `envelope-jars.md`, `pay-yourself-first.md`, `emergency-fund.md`, `sinking-funds.md`, `debt-basics.md`
- [x] T5 Implement ingest script idempotent theo `content_hash`
- [x] T6 Implement `knowledge_service.search` dùng pgvector cosine + metadata citation
- [x] T7 Add Coach tool `search_knowledge` và update Coach prompt/guard
- [x] T8 Golden tests: citations, personal-data tool required khi hỏi "có phù hợp với tao không"
- [x] T9 Retrieval eval hit@3 với 12 queries
- [x] T10 UI citations trong `/coach`
- [x] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-16: rag knowledge`

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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] Knowledge base là nội dung tự viết, không sao chép tài liệu có bản quyền
- [x] Coach bắt buộc gọi personal-data tool khi user hỏi mức độ phù hợp cá nhân
- [x] Câu trả lời kiến thức có `Nguồn:` và citation thật
- [x] Retrieval eval hit@3 đạt ngưỡng
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền, đánh dấu M6
- [x] Commit `phase-16: rag knowledge`

## 8. Rủi ro / câu hỏi mở

- Tokenizer chính xác có thể cần thêm dependency; nếu chưa có, dùng ước lượng theo từ và ghi rõ trong handoff.
- Câu hỏi tiếng Việt đời thường có thể cần synonyms trong golden set ("quỹ dự phòng", "tiền phòng thân").
- Không được copy nguyên văn sách/blog; chỉ viết lại bằng lời của dự án.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22
- **Đã làm:**
  - **Migration** `20261022_e86dd65f1762_rag_knowledge`: `knowledge_documents` (`source` unique, `source_type` CHECK, `content_hash` UNIQUE, `metadata`), `knowledge_chunks` (FK CASCADE, UNIQUE `(document_id, chunk_index)`, `vector(1536)` + HNSW cosine, `metadata` heading_path / headings / tags / pages), `chat_messages.citations JSONB`. ORM `models/knowledge.py`. Dependency mới `pypdf>=5` (venv 6.21.2). `alembic check` sạch, downgrade / upgrade chạy được.
  - **Knowledge base tự viết** `backend/knowledge/`: `50-30-20.md`, `envelope-jars.md`, `pay-yourself-first.md`, `emergency-fund.md`, `sinking-funds.md`, `debt-basics.md` (front matter title / tags / language; nội dung viết lại bằng lời của dự án, có liên hệ khái niệm trong app như loại chi tiêu, mục tiêu, PYF).
  - **Deterministic:** `services/knowledge_chunking` (đọc markdown + front matter, PDF qua `pypdf` theo trang; chia đoạn ≤ 800 token ước lượng, cắt ở ranh giới mục khi ≥ 500, overlap ~100 token khi cắt giữa mục, gộp đoạn cuối quá ngắn; `embedding_text`, `citation`), `services/knowledge_service` (ingest idempotent theo `content_hash` + đổi tên + bỏ trùng + `prune`; `search` cosine + ngưỡng 0.3; `search_for_coach`; `get_chunk`; `list_documents`; `resolve_ingest_path` chống path traversal), `repositories/knowledge_repository`.
  - **API** `GET /knowledge/search?q=&limit=`, `GET /knowledge/documents`, `GET /knowledge/chunks/{id}`, `POST /knowledge/reindex {path?, prune}`; script `python -m app.scripts.ingest_knowledge [path] [--prune]`. `ai/embeddings.embed_knowledge`.
  - **Coach:** tool thứ 8 `search_knowledge` (read-only), prompt `coach_v4.md` (kiến thức chỉ từ thư viện, mục **Nguồn:**, bắt buộc tool số liệu khi hỏi mức độ phù hợp, không tìm thấy → nói rõ), `get_spending_summary` thêm `income_share_pct` / `net_income_pct` (service tính) để so với 50/30/20 mà không tự tính. Guard: số trong văn bản kiến thức được phép; `check_citations` (thiếu mục Nguồn / nguồn không có trong kết quả → viết lại); `check_tool_usage` (câu hỏi "phù hợp với tao / của tao / tao nên…" đã tra kiến thức mà chưa có tool số liệu → viết lại); fallback liệt kê nguồn thật. `coach_evidence.select_citations` → `CoachAnswer.citations` → lưu `chat_messages.citations`, trả trong `ChatMessageRead` / `CoachMessageResponse`. Tool trace "Đã tra kiến thức: … (n đoạn)".
  - **Frontend** `/coach`: `CitationList` (khối "Nguồn (n)" thu gọn được, S1…, tiêu đề — mục + đường dẫn; ẩn mục Nguồn trùng trong văn bản) + drawer (Dialog) toàn văn đoạn từ `GET /knowledge/chunks/{id}`; câu gợi ý "50/30/20 là gì, có phù hợp với tao không?"; nhãn tool mới. `gen:api` chạy lại.
  - **Test:** **1130 pass** (+35, không cần key): `tests/unit/test_knowledge_chunking.py` (front matter / heading, 6 tài liệu ≥ 12 đoạn ≤ 800 token, overlap, cắt ở ranh giới mục, gom mục nhỏ, gộp đuôi ngắn, PDF 3 trang + lỗi PDF, guard nguồn / dữ liệu cá nhân / số kiến thức / fallback), `tests/api/test_knowledge_search.py` (test case 1, 2, 3 (embedding giả), 5–7 với model giả, ingest idempotent không gọi AI lần 2, đổi tên / prune / trùng nội dung, PDF + file lỗi, API search / chunk / documents / reindex + chặn `../`, 503 thiếu key, tool output). `tests/pdf_helper.py` sinh PDF có lớp chữ không cần thư viện. Fixture `fake_llm` chuyển sang `tests/api/conftest.py` (dùng chung).
  - **Golden (`pytest -m ai`, text-embedding-3-small + gpt-4o, 2026-10-22):** `tests/ai_golden/test_rag_coach.py` — retrieval 12 câu hỏi đời thường **hit@3 = 12/12 (1,00)** (ngưỡng 0,80); Coach: "50/30/20 là gì?" có nguồn 50/30/20 (passed); "… có phù hợp với tao không" gọi `search_knowledge` + `get_spending_summary` (passed); "Pay yourself first khác gì 50/30/20?" có nguồn cả hai (rewritten — lần đầu dùng cụm cấm "bắt buộc phải"); "quỹ khẩn cấp của tao nên bao nhiêu" (rewritten — guard bắt số tự nhân 12.600.000 / 25.200.000); "FIRE 4%" → "chưa tìm thấy nguồn", không citation. Toàn bộ `pytest -m ai`: **32/32**.
- **Lệch so với plan (và lý do):**
  - Token **ước lượng** = số ký tự / 3 (chưa thêm `tiktoken` — cần tải bảng mã lúc chạy, không hợp CI offline); rủi ro mục 8 cho phép.
  - Overlap ~100 token chỉ áp dụng khi cắt **giữa một mục**; cắt ở ranh giới mục không overlap (heading đã đủ ngữ cảnh) — tránh lặp nội dung giữa các mục ngắn.
  - Thêm `chat_messages.citations`, `KnowledgeChunkRead`, `GET /knowledge/documents`, `GET /knowledge/chunks/{id}` (drawer cần toàn văn), `KnowledgeReindexResult` chi tiết (`created/updated/unchanged/skipped/removed/errors`) thay vì `{documents, chunks}`; reindex nhận `prune`.
  - `knowledge_documents.source` unique + đổi tên giữ embedding; file trùng nội dung bỏ qua (do `content_hash` UNIQUE).
  - Không dùng schema `CoachAnswerWithCitations` (observation / explanation / action / citations) — Coach vẫn trả văn bản tự do có cấu trúc (như Phase 10) + `citations` có cấu trúc do backend dựng từ mục Nguồn (guard kiểm tra), giữ nguyên luồng function calling.
  - Ngưỡng `MIN_KNOWLEDGE_SCORE = 0.3` không đủ để lọc câu hỏi ngoài thư viện (FIRE vẫn ~0,5) → "không tìm thấy" do prompt + guard chống bịa nguồn đảm bảo.
  - `get_spending_summary` thêm 2 trường % theo thu nhập (cần cho câu hỏi 50/30/20 cá nhân).
- **Nợ kỹ thuật / TODO để lại:**
  - Chưa có tokenizer thật; chưa hybrid từ khoá cho kiến thức; chưa re-rank.
  - Câu hỏi "quỹ khẩn cấp của tao" model hay tự nhân số tháng × chi thiết yếu → guard chặn, viết lại tốn thêm 1 lượt; có thể thêm trường deterministic (vd mức quỹ 3 / 6 tháng) vào tool sau này.
  - Thư viện kiến thức chỉ 6 bài / 12 đoạn; thêm bài cần chạy lại ingest (UI chưa upload — ngoài scope).
- **Lệnh hữu ích:**
  ```bash
  (cd backend && python -m app.scripts.ingest_knowledge knowledge/)
  (cd backend && pytest tests/unit/test_knowledge_chunking.py tests/api/test_knowledge_search.py)
  (cd backend && pytest -m ai -s tests/ai_golden/test_rag_coach.py)
  curl "http://localhost:8000/api/v1/knowledge/search?q=quỹ%20khẩn%20cấp&limit=3"
  ```
- **Gợi ý cho phase tiếp theo:** Phase 17 đăng ký tool `simulate` vào `finance_tools.default_registry()` (cập nhật `TOOLS` ở `tests/api/test_coach.py` + danh sách ở `test_coach_tools.py`); nếu narrative simulator dùng `structured_completion`, tái dùng `review_narrative.extract_numbers` / `contains_phrase` / `has_conditional` để validate số và giọng văn như advice Phase 8.
