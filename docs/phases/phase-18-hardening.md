# Phase 18 — Hardening & Wrap-up

| | |
|---|---|
| **ID** | `phase-18-hardening` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 9, 12, 13, 14, 16, 17 phải Done |
| **Mở khoá** | — |
| **Milestone** | **M7 — Hoàn thiện** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + toàn bộ Handoff notes còn nợ
2. [vision.md](../product/vision.md) — core loop và nguyên tắc không phán xét
3. [feature-map.md](../product/feature-map.md) — đối chiếu feature đã hoàn tất
4. [overview.md](../architecture/overview.md), [containers.md](../architecture/containers.md)
5. [backend-components.md](../architecture/backend-components.md), [frontend-structure.md](../architecture/frontend-structure.md)
6. [data-model.md](../architecture/data-model.md), [ai-architecture.md](../architecture/ai-architecture.md), [sequences.md](../architecture/sequences.md)
7. ADR [001](../architecture/decisions/ADR-001-fastapi-nextjs.md), [002](../architecture/decisions/ADR-002-postgres-pgvector.md), [004](../architecture/decisions/ADR-004-single-user-first.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: tất cả phase chức năng 0–17 đã chạy được, nhưng còn nợ edge cases, docs drift, coverage, Docker full compose và CI.

## 2. Mục tiêu & giá trị cho user

Đưa dự án từ "demo nhiều tính năng" thành bản hoàn thiện có thể chạy lại ổn định: test đủ, lỗi rõ ràng, bảo mật local hợp lý, Docker/CI có, README/demo script đầy đủ.

## 3. Scope

**In scope**
- Coverage target services ≥ 85% bằng `pytest-cov`.
- Review edge cases xuyên suốt các phase.
- Error handling/logging nhất quán; dashboard đơn giản theo dõi token usage/cost AI.
- Security review: secrets, upload validation, CORS, SQL injection qua ORM, prompt injection trong notes/receipts/knowledge.
- Performance review: indexes, N+1, vector search limits.
- Dockerfile backend/frontend + full `docker-compose.yml` chạy db/backend/frontend.
- GitHub Actions CI: ruff, pytest không chạy AI, npm lint/build.
- Optional auth decision theo ADR-004 follow-up.
- Sync docs kiến trúc với thực tế, README hoàn chỉnh, demo script end-to-end.
- Manual smoke checklist toàn bộ core loop.

**Out of scope**
- Deploy production public.
- Mobile app native.
- Multi-currency/investment/tax.
- Viết lại kiến trúc lớn; chỉ hardening và wrap-up.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Không thêm bảng nghiệp vụ bắt buộc. Nếu cần AI cost dashboard bền vững, thêm `ai_call_logs`: `id`, `task`, `model`, `input_tokens`, `output_tokens`, `cost_estimate`, `latency_ms`, `status`, `created_at`, `metadata JSONB`. Nếu đã log ra file/structured logs ở phase trước, dashboard có thể đọc từ DB/log hiện có.

Auth follow-up (optional, chỉ nếu quyết định bật multi-user):
- `users` bảng tối thiểu hoặc tích hợp provider auth.
- Các `user_id` chuyển `NOT NULL` sau backfill single default user.
- Unique constraints theo kỳ đổi từ `period_month`, `week_start`, `month`, `file_hash` sang `(user_id, ...)` nơi phù hợp.
- Không bật auth nửa vời; nếu không đủ thời gian, ghi rõ app chỉ local single-user.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/health` | Health tổng hợp backend/db/vector/openai configured | — | `{status, db, vector, ai_configured, version}` |
| GET | `/api/v1/admin/ai-usage` | Bảng token/cost đơn giản | `from?, to?, group_by=model|task` | `{totals, rows}` |
| GET | `/api/v1/admin/smoke-data` | Dev-only kiểm tra seed/demo data đủ | — | `{ok, missing:[...]}` |

Hardening checklist backend:
- Error codes nhất quán `{"detail","code"}`.
- Upload validation: MIME + extension + size + image/PDF sniff cơ bản.
- ORM parameter binding; không concat raw SQL cho search/filter.
- Prompt injection: notes/receipt/knowledge luôn đưa vào prompt như data, không instruction; Coach system prompt ưu tiên guardrails.
- Rate/cost guard: max rows import classify, max file size, max tool calls Coach, max chunks RAG.

### 4.3 AI

- Env bắt buộc documented: `OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_API_KEY`.
- Golden tests `pytest -m ai` vẫn tách khỏi CI mặc định; README ghi cách chạy có key.
- Prompt review: mọi prompt sinh văn bản tuân thủ Observation → Explanation → Action, cấm phán xét.
- Pydantic schema audit:
```python
class AIUsageRow(BaseModel):
    task: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_estimate: Decimal
    latency_ms_avg: int
    error_count: int

class SmokeCheckResult(BaseModel):
    ok: bool
    area: str
    message: str
```
- Guardrails regression: tests keyword cấm ("bạn phải", "lãng phí", "quá nhiều") cho review/coach/simulator.

### 4.4 Frontend

- Build production bằng `npm run build`.
- Error boundary/global toast cho API errors.
- `/settings` hoặc admin section hiển thị AI usage table: task/model/tokens/cost/error.
- README screenshots hoặc mô tả demo route chính.
- Responsive smoke tối thiểu cho `/transactions`, `/budget`, `/coach`, `/import`, `/simulator`.

## 5. Task breakdown

- [ ] T1 Chạy baseline test/lint/build, lập danh sách lỗi/nợ từ Handoff notes
- [ ] T2 Thêm/cấu hình `pytest-cov`, nâng coverage `services/` ≥ 85%
- [ ] T3 Edge case pass: money/date/timezone, empty data, duplicate, missing AI key, upload lỗi, vector không có dữ liệu
- [ ] T4 Chuẩn hoá error handling/logging + AI usage logging/dashboard
- [ ] T5 Security review và fix: secrets, CORS, upload, ORM injection, prompt injection, file path traversal
- [ ] T6 Performance review: indexes, N+1, pagination/limit, vector query explain
- [ ] T7 Dockerfile backend/frontend + full compose db/backend/frontend + healthchecks
- [ ] T8 GitHub Actions CI: backend ruff/pytest non-AI, frontend lint/build
- [ ] T9 Optional auth decision: implement hoặc ghi ADR-004 follow-up rõ ràng
- [ ] T10 Sync docs architecture/data-model/sequences/README với reality
- [ ] T11 Viết demo script end-to-end với seed data
- [ ] T12 Manual smoke checklist toàn bộ flow
- [ ] T13 Cập nhật docs/PROGRESS/handoff + commit `phase-18: hardening`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
docker compose up -d --build
curl http://localhost:8000/api/v1/health

cd backend
ruff check .
pytest --cov=app.services --cov-report=term-missing --cov-fail-under=85
pytest -m "not ai"
pytest -m ai

cd ..\frontend
npm run lint
npm run build
```

**Test cases / review checklist**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Không có `OPENAI_API_KEY` | CRUD/budget/search UI deterministic không crash; AI endpoint trả lỗi rõ |
| 2 | Upload `.exe` đổi tên `.csv` | 400 `INVALID_FILE_TYPE` |
| 3 | CSV import lại cùng file | 409 hoặc skip duplicate, không nhân đôi transaction |
| 4 | Note chứa prompt injection "ignore previous instructions" | Coach coi là dữ liệu, không đổi system behavior |
| 5 | Search query dài 5.000 ký tự | 422 hoặc truncate an toàn, không raw SQL lỗi |
| 6 | DB rỗng | Dashboard/review/coach trả empty state thân thiện |
| 7 | 1.000 transactions | `/transactions`, `/budget`, `/search` vẫn phân trang/limit hợp lý |
| 8 | Services coverage | `pytest-cov` báo ≥ 85% cho `app.services` |
| 9 | Docker compose full | FE gọi BE, BE gọi DB, health OK |
| 10 | CI push | ruff, pytest non-AI, npm lint/build xanh |

**Kịch bản smoke UI end-to-end**
1. Seed demo data.
2. Transaction: thêm/sửa/xoá 1 giao dịch thủ công và 1 quick add NL.
3. Budget: tạo budget 50/30/20, xem Budget vs Actual + flexible zones.
4. Weekly review → nhập reflection; Monthly review → xem breakdown.
5. Advisor: xem budget advice và dismiss/accept nếu có.
6. Coach: hỏi "Tao nên giảm khoản nào?" → tool calls + evidence.
7. Goals/PYF: tạo goal laptop, nhập lương, allocate saving.
8. Calendar: xem recurring/forecast.
9. OCR: upload receipt fixture, confirm draft.
10. Import: upload CSV fixture, preview/bulk edit/commit.
11. Search: query "ăn ngoài" thấy semantic results.
12. RAG: hỏi "50/30/20 có phù hợp với tao không" thấy citations + dữ liệu cá nhân.
13. Simulator: giảm ăn ngoài 20%, thấy goal sớm hơn 9 ngày.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `docker compose up -d --build` chạy full stack sạch trên máy mới
- [ ] Services coverage ≥ 85%, CI xanh không cần OpenAI key
- [ ] Security/performance review đã xử lý hoặc ghi TODO có lý do
- [ ] README có setup, env, test, AI golden, demo script
- [ ] Architecture docs synced với schema/API thực tế
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền, đánh dấu M7
- [ ] Commit `phase-18: hardening`

## 8. Rủi ro / câu hỏi mở

- Nếu nhiều phase trước chưa cập nhật `data-model.md`, Phase 18 có thể tốn thời gian sync docs hơn code.
- Docker build frontend cần env `NEXT_PUBLIC_API_BASE_URL` đúng cho browser (`http://localhost:8000/api/v1`), không dùng tên service nội bộ.
- Auth là quyết định lớn: nếu không hoàn tất trọn vẹn, tốt hơn giữ single-user local và ghi rõ theo ADR-004.
- AI cost estimate phụ thuộc giá model hiện tại; nên ghi là estimate và tách config giá.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
