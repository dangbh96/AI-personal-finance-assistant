# Phase 15 — Semantic Spending Search

| | |
|---|---|
| **ID** | `phase-15-semantic-search` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 1 phải Done |
| **Mở khoá** | Phase 16 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 1
2. [glossary.md](../product/glossary.md) — `Transaction`, category, spending type
3. [feature-map.md](../product/feature-map.md) — pgvector thay Pinecone trong course
4. [data-model.md](../architecture/data-model.md) — `TRANSACTION_EMBEDDING`, HNSW index
5. [backend-components.md](../architecture/backend-components.md) — `ai/embeddings`, router `search`, Coach tools
6. [frontend-structure.md](../architecture/frontend-structure.md) — route `/search`
7. [ai-architecture.md](../architecture/ai-architecture.md) — `OPENAI_EMBEDDING_MODEL`, tool `search_transactions`
8. [sequences.md](../architecture/sequences.md#tìm-kiếm-ngữ-nghĩa-phase-15)
9. ADR [002](../architecture/decisions/ADR-002-postgres-pgvector.md), [003](../architecture/decisions/ADR-003-openai-primary-llm.md)

Trạng thái code giả định: Phase 1 có CRUD transaction/category ổn định; nếu Phase 3 đã xong thì có thể tận dụng preference cho classifier nhưng không bắt buộc.

## 2. Mục tiêu & giá trị cho user

User tìm được giao dịch theo ý nghĩa tiếng Việt, ví dụ "ăn ngoài" trả về note "nhà hàng", "quán nướng", "bún chả"; "đi lại" trả về "grab", "xăng", dù không trùng keyword.

## 3. Scope

**In scope**
- Migration `CREATE EXTENSION IF NOT EXISTS vector`.
- Bảng `transaction_embeddings` với `vector(1536)`, HNSW cosine index.
- Tạo embedding khi transaction create/update (sync best-effort; lỗi embedding không block lưu giao dịch).
- Backfill command `python -m app.scripts.backfill_embeddings`.
- API `GET /api/v1/search/transactions?q=&from=&to=&limit=` trả results + tổng tiền.
- Hybrid search: vector similarity + `ILIKE` keyword boost.
- Coach tool `search_transactions`.
- Golden test semantic search với precision@10.
- Tài liệu mapping Pinecone concepts → pgvector: index/upsert/query/metadata filter.

**Out of scope**
- Semantic search cho knowledge base (Phase 16).
- Full-text search tiếng Việt có unaccent ranking nâng cao.
- Re-rank bằng LLM.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Migration:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

`transaction_embeddings`: `transaction_id UUID PRIMARY KEY FK transactions(id) ON DELETE CASCADE`, `embedding vector(1536) NOT NULL`, `content TEXT NOT NULL`, `model TEXT NOT NULL`, `embedded_at timestamptz NOT NULL`.

Index:
```sql
CREATE INDEX ix_transaction_embeddings_embedding_hnsw
ON transaction_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

Content để embed (quyết định):
`"{note}. Danh mục: {category.name}. Khoản {amount_bucket}. Loại: {spending_type|thu nhập}."`

`amount_bucket`: `<100k`, `100k-500k`, `500k-2m`, `2m-10m`, `>10m`. Không embed số tiền chính xác để giảm noise nhưng vẫn giúp tìm "khoản lớn".

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/search/transactions` | Tìm giao dịch semantic + keyword | `q`, `from?`, `to?`, `limit=20` | `{query, total_amount, results:[...]}` |
| POST | `/api/v1/search/transactions/reindex` | Dev-only backfill nhanh qua API nếu cần | `{transaction_ids?:[]}` | `{queued_or_processed_count}` |

`ai/embeddings.py` bọc OpenAI embeddings, đọc `OPENAI_EMBEDDING_MODEL`, timeout/retry qua `openai_client`.

`services/embedding_service.py`:
- `build_transaction_embedding_content(transaction, category)`.
- `embed_transaction_best_effort(db, transaction_id)`: catch/log lỗi, không raise lên transaction create/update.
- `backfill_missing(limit, batch_size)`.

Hybrid scoring:
- Lấy top `limit * 5` bằng vector distance `<=>`.
- Keyword boost nếu `transactions.note ILIKE %q%` hoặc `categories.name ILIKE %q%`.
- `score = 0.75 * (1 - cosine_distance) + 0.25 * keyword_boost`, keyword_boost `1.0` nếu note match, `0.5` nếu category match, `0` nếu không.
- Filter ngày/category chạy ở SQL trước khi limit cuối.

Pydantic schemas:
```python
class TransactionSearchResult(BaseModel):
    transaction_id: UUID
    occurred_on: date
    note: str
    amount: int
    direction: Literal["income", "expense"]
    category_name: str
    spending_type: Literal["essential", "non_essential", "irregular"] | None
    score: float
    match_reason: Literal["semantic", "keyword", "hybrid"]

class TransactionSearchResponse(BaseModel):
    query: str
    from_date: date | None
    to_date: date | None
    total_amount: int
    results: list[TransactionSearchResult]
```

### 4.3 AI

- Embedding model: `OPENAI_EMBEDDING_MODEL` (mặc định `text-embedding-3-small`, 1536 dim).
- Chat models không cần cho search endpoint. `OPENAI_MODEL_FAST` chỉ dùng nếu Phase 3 classifier muốn dùng vector similarity preference như optional memory.
- Prompt outline: không có LLM prompt; input embedding là chuỗi content đã sanitize. Không gửi dữ liệu ngoài note/category/bucket cần thiết.
- Optional Phase 3 extension: embed `classification_preferences.example_text`; khi exact keyword không match, tìm preference gần nhất bằng vector similarity và đưa top-5 vào classifier.
- Guardrails: embedding lỗi không làm fail CRUD; search trả 503 nếu query embedding lỗi; không dùng AI để tự tính tổng tiền, `total_amount` tính bằng SQL/Python.

### 4.4 Frontend

- Route `/search`: search box tiếng Việt, filter date range, limit selector 10/20/50.
- `SearchResultList`: note, ngày, category badge, amount, score/match reason nhỏ.
- Summary card: tổng thu, tổng chi, net của kết quả hiện tại (backend trả `total_amount` cho direction-filter hoặc FE tách thu/chi nếu API trả cả hai).
- Empty state: hướng dẫn ví dụ "ăn ngoài", "đi lại", "khoản lớn mua sắm".

## 5. Task breakdown

- [ ] T1 Migration `vector`, bảng `transaction_embeddings`, HNSW index cosine
- [ ] T2 Implement `ai/embeddings.py` + settings `OPENAI_EMBEDDING_MODEL`
- [ ] T3 Implement content builder + amount bucket + unit tests
- [ ] T4 Hook best-effort embed vào transaction create/update/delete cascade
- [ ] T5 Script `python -m app.scripts.backfill_embeddings --batch-size 100`
- [ ] T6 Implement SQL hybrid search + API schemas/router
- [ ] T7 Add Coach tool `search_transactions(q, from_date, to_date, limit)` read-only
- [ ] T8 Golden dataset + `pytest -m ai` precision@10 tests
- [ ] T9 UI `/search` + filters + result list
- [ ] T10 Docs note Pinecone concepts mapping + update progress/handoff
- [ ] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-15: semantic search`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
(cd backend && alembic upgrade head && ruff check . && pytest tests/unit/test_embedding_content.py tests/api/test_transaction_search.py)
(cd backend && python -m app.scripts.backfill_embeddings --batch-size 50)
(cd backend && pytest -m ai tests/ai_golden/test_semantic_search.py)
(cd frontend && npm run gen:api && npm run lint && npm run dev)
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Tạo transaction "Bún chả Hàng Mành" | Transaction lưu 201 dù embedding API bị mock lỗi |
| 2 | Backfill 12 transactions thiếu embedding | Tạo đủ 12 rows `transaction_embeddings` |
| 3 | Update note transaction | `content` và `embedded_at` đổi |
| 4 | Query `ăn ngoài`, dataset có "nhà hàng", "quán nướng", "bún chả" | 3 dòng này nằm top 10, precision@10 ≥ 0.70 |
| 5 | Query `đi lại`, dataset có "grab về nhà", "đổ xăng", "vé xe bus" | 3 dòng này nằm top 10 |
| 6 | Query `ăn ngoài` + `from=2026-09-01&to=2026-09-30` | Không trả dòng ngoài tháng 9 |
| 7 | Keyword exact "Highlands" | Dòng note Highlands được boost lên top 3 |
| 8 | Không có `OPENAI_API_KEY` khi search | 503 `AI_UNAVAILABLE`, app không crash |

**Kịch bản thao tác UI**
1. Mở `/search`, nhập "ăn ngoài tháng này" với date range tháng hiện tại → thấy nhà hàng/quán/bún chả.
2. Đổi range sang tháng trước → kết quả thay đổi, tổng tiền cập nhật.
3. Nhập "grab xăng" → thấy các giao dịch đi lại, không cần đúng keyword đầy đủ.
4. Click 1 kết quả → điều hướng/hiển thị chi tiết transaction.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` thường không cần API key; `pytest -m ai` đạt precision@10 threshold khi có key
- [ ] CRUD transaction vẫn thành công khi embedding lỗi
- [ ] HNSW index được tạo và query dùng cosine distance
- [ ] Coach tool `search_transactions` đăng ký nhưng read-only
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-15: semantic search`

## 8. Rủi ro / câu hỏi mở

- pgvector HNSW cần Postgres/pgvector version phù hợp; nếu local image cũ, fallback IVFFlat hoặc update image.
- Query tiếng Việt có dấu/không dấu có thể chưa hoàn hảo; hybrid ILIKE chưa unaccent.
- Embedding mỗi update có chi phí; hiện sync best-effort đơn giản, sau này có thể chuyển job queue.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
