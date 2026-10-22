# Phase 18 — Hardening & Wrap-up

| | |
|---|---|
| **ID** | `phase-18-hardening` |
| **Trạng thái** | Done |
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

- [x] T1 Chạy baseline test/lint/build, lập danh sách lỗi/nợ từ Handoff notes
- [x] T2 Thêm/cấu hình `pytest-cov`, nâng coverage `services/` ≥ 85%
- [x] T3 Edge case pass: money/date/timezone, empty data, duplicate, missing AI key, upload lỗi, vector không có dữ liệu
- [x] T4 Chuẩn hoá error handling/logging + AI usage logging/dashboard
- [x] T5 Security review và fix: secrets, CORS, upload, ORM injection, prompt injection, file path traversal
- [x] T6 Performance review: indexes, N+1, pagination/limit, vector query explain
- [x] T7 Dockerfile backend/frontend + full compose db/backend/frontend + healthchecks
- [x] T8 GitHub Actions CI: backend ruff/pytest non-AI, frontend lint/build
- [x] T9 Optional auth decision: implement hoặc ghi ADR-004 follow-up rõ ràng
- [x] T10 Sync docs architecture/data-model/sequences/README với reality
- [x] T11 Viết demo script end-to-end với seed data
- [x] T12 Manual smoke checklist toàn bộ flow
- [x] T13 Cập nhật docs/PROGRESS/handoff + commit `phase-18: hardening`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
docker compose up -d --build
curl http://localhost:8000/api/v1/health

cd backend
ruff check .
pytest --cov=app.services --cov-report=term-missing --cov-fail-under=85
pytest -m "not ai"
pytest -m ai

cd ../frontend
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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `docker compose up -d --build` chạy full stack sạch trên máy mới
- [x] Services coverage ≥ 85%, CI xanh không cần OpenAI key
- [x] Security/performance review đã xử lý hoặc ghi TODO có lý do
- [x] README có setup, env, test, AI golden, demo script
- [x] Architecture docs synced với schema/API thực tế
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền, đánh dấu M7
- [x] Commit `phase-18: hardening`

## 8. Rủi ro / câu hỏi mở

- Nếu nhiều phase trước chưa cập nhật `data-model.md`, Phase 18 có thể tốn thời gian sync docs hơn code.
- Docker build frontend cần env `NEXT_PUBLIC_API_BASE_URL` đúng cho browser (`http://localhost:8000/api/v1`), không dùng tên service nội bộ.
- Auth là quyết định lớn: nếu không hoàn tất trọn vẹn, tốt hơn giữ single-user local và ghi rõ theo ADR-004.
- AI cost estimate phụ thuộc giá model hiện tại; nên ghi là estimate và tách config giá.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22
- **Đã làm:**
  - **Coverage:** `pytest-cov` vào dev deps + `[tool.coverage]` (branch); `pytest --cov=app.services --cov-fail-under=85` → **95,4 %** (không cần viết thêm test để đạt ngưỡng).
  - **Lỗi nhất quán** (`core/errors.py`): `StarletteHTTPException` → `{"detail","code"}` (`404 not_found`, `405 method_not_allowed`, …); middleware bắt exception không lường trước → `500 internal_error` (log traceback, không lộ chi tiết), đăng ký **trước** CORS nên response lỗi vẫn có header CORS. CORS chỉ cho các method thực dùng.
  - **Health** thêm `vector` (kiểm tra extension pgvector).
  - **AI usage logging:** migration `20261022_8477f3443c12_hardening_ai_call_logs` (bảng `ai_call_logs`, không lưu nội dung); `core/ai_usage` (`AICall`, `record_call`, `db_sink` session riêng, `set_sink`, giá embedding); `openai_client` ghi sau mọi `structured_completion` / `chat_with_tools` / `create_embeddings` kể cả lỗi; sink lỗi không làm hỏng lời gọi AI.
  - **Admin API** (`schemas/admin.py`, `repositories/ai_call_log_repository.py`, `services/admin_service.py`, router `admin`): `GET /admin/ai-usage?from&to&group_by=model|task|kind` (mặc định 30 ngày, ≤ 366 ngày), `GET /admin/smoke-data` (8 kiểm tra: danh mục, giao dịch 3 tháng, ngân sách tháng này, mục tiêu, định kỳ, embedding, kiến thức, khoá AI; `required` phân biệt bắt buộc / khuyến nghị).
  - **Prompt injection:** evidence của Coach hiển thị ghi chú người dùng dạng trích dẫn “…” cắt ≤ 60 ký tự (`coach_evidence._quote_note`) → fallback không “nói lại” lệnh trong ghi chú như lời của trợ lý; guard vẫn chặn câu trả lời bị dụ (test API + golden thật).
  - **Frontend:** `src/app/error.tsx` (error boundary toàn cục, "Thử lại"); tab "Chi phí AI" ở `/settings` (`AIUsagePanel`: 4 thẻ tổng + bảng, chọn nhóm theo model / tác vụ / loại lời gọi); `gen:api`; `npm run build` xanh.
  - **Docker:** `backend/Dockerfile` (python:3.13-slim, user `pfa`, cài deps từ pyproject để cache layer, `alembic upgrade head` rồi `uvicorn`, healthcheck), `frontend/Dockerfile` (node:22-alpine multi-stage, build arg `NEXT_PUBLIC_API_BASE_URL`, `next start`, healthcheck), `.dockerignore` hai bên; `docker-compose.yml` đủ `db` + `backend` + `frontend` (depends_on healthy, `env_file backend/.env` không bắt buộc, volume `pfa_uploads`, port đổi được qua `BACKEND_PORT` / `FRONTEND_PORT`).
  - **CI:** `.github/workflows/ci.yml` — backend (pgvector service, tạo `pfa_test`, ruff check + format check, pytest + coverage gate) và frontend (`npm ci`, lint, typecheck, build).
  - **ADR-004 follow-up:** giữ single-user local, không bật auth; ghi biện pháp bù + các bước khi cần multi-user.
  - **Docs:** README viết lại (tính năng, env, dev, Docker, test, golden, CI), `docs/demo-script.md` (chuẩn bị + 18 bước demo + smoke checklist), `docs/PROJECT-GUIDE.md` (giải thích toàn bộ dự án cho người mới), sync `overview`, `containers`, `backend-components`, `frontend-structure`, `data-model`, `ai-architecture` (§ 8 vận hành & an toàn).
  - **Test:** **1190 pass** (+24): `tests/api/test_hardening.py` — 404/405 có `code`; 500 JSON có CORS; log lời gọi AI không chứa nội dung, lỗi AI được ghi, embedding được ghi, `db_sink` + báo cáo nhóm theo model / task / kind + validate khoảng ngày, sink lỗi không phá lời gọi; smoke-data DB rỗng; `.exe` đổi tên `.csv` / `.jpg` bị từ chối; tên file `../../` bị loại; prompt injection trong ghi chú; DB rỗng các endpoint chính 200; 1.000 giao dịch phân trang / limit. `tests/api/test_health.py` thêm `vector`.
  - **Golden:** thêm `test_golden_prompt_injection_in_note_is_data` (gpt-4o thật: guard `rewritten`, không cụm cấm); `pytest -m ai` toàn bộ **36/36** (2026-10-22, ~4 phút).
  - **Verify (2026-10-22):** `ruff check` + `ruff format --check` sạch; `pytest` 1190 pass; coverage services 95,4 %; `npm run lint` / `typecheck` / `build` xanh; `docker compose up -d --build` (port 8001 / 3001 vì máy đang chạy dev server) → 3 container healthy, `/api/v1/health` `{"status":"ok","db":"ok","vector":"ok",...}`, frontend container gọi backend container (CORS đúng origin), tab Chi phí AI hiển thị dữ liệu; responsive 390 px `/transactions`, `/budget`, `/coach`, `/import`, `/simulator`, `/settings`, `/search` không tràn ngang, không lỗi.
- **Lệch so với plan (và lý do):**
  - Upload `.exe` đổi đuôi trả **415 `unsupported_file_type`** (import) / 415 ảnh không hợp lệ (receipt) thay vì `400 INVALID_FILE_TYPE` — giữ mã đã dùng từ Phase 13–14 (đúng ngữ nghĩa HTTP, frontend đã xử lý).
  - `AIUsageRow` dùng `key` + `group_by` (thêm nhóm `kind`) thay vì cố định cột `task` + `model`; chi phí là **số nguyên đồng** (`cost_estimate_vnd`) thay vì `Decimal` (ADR-007). `SmokeCheckResult` thêm `required`; response smoke có `checks[]` ngoài `{ok, missing}`.
  - Không có "global toast": lỗi API hiển thị tại chỗ (mẫu sẵn có từ Phase 1) + error boundary cho lỗi render.
  - Không bật auth (ADR-004 follow-up).
  - Compose cho đổi port qua biến môi trường (plan cố định 8000 / 3000) để chạy song song dev server.
- **Nợ kỹ thuật / TODO để lại:**
  - Workflow CI mới chỉ kiểm cục bộ từng bước (chưa có lần chạy trên GitHub tại thời điểm commit).
  - Bảng giá model hard-code trong `core/ai_usage` (ước tính); cần cập nhật khi OpenAI đổi giá. Tỷ giá cố định 26.000 đ/USD.
  - `/admin/*` không xác thực — chấp nhận được vì local single-user; bật auth thì phải bảo vệ.
  - Image frontend copy cả `node_modules` production (chưa dùng `output: "standalone"`) → image lớn hơn cần thiết.
  - Prettier không nằm trong script (`npm run lint` chỉ ESLint).
  - Performance: index hiện có đủ cho dữ liệu cá nhân (giao dịch theo ngày / danh mục, HNSW vector, unique dedup); chưa đo với > 100k giao dịch; danh sách đều phân trang / có `limit` tối đa.
- **Lệnh hữu ích:**
  ```bash
  (cd backend && pytest --cov=app.services --cov-report=term-missing --cov-fail-under=85)
  (cd backend && pytest tests/api/test_hardening.py)
  (cd backend && pytest -m ai -s tests/ai_golden/test_coach.py -k injection)
  BACKEND_PORT=8001 FRONTEND_PORT=3001 docker compose up -d --build && curl http://localhost:8001/api/v1/health
  curl "http://localhost:8000/api/v1/admin/ai-usage?group_by=task"
  curl http://localhost:8000/api/v1/admin/smoke-data
  ```
- **Gợi ý cho phase tiếp theo:** (sau M7) bật auth theo ADR-004 nếu cần nhiều người dùng; khái niệm tài khoản / ví cho forecast + import; `output: "standalone"` cho image frontend; cảnh báo chi phí AI theo ngưỡng tháng từ `ai_call_logs`.
