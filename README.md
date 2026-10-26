# AI Personal Finance Assistant — "Personal CFO"

Trợ lý tài chính cá nhân giúp người dùng **hiểu tiền của mình đang đi đâu, lập kế hoạch sử dụng tiền, rồi định kỳ review để cải thiện hành vi tài chính**.

Core loop: **Income → Pay Yourself First → Budget → Track → Classify → Actual vs Budget → Weekly/Monthly Review → Điều chỉnh**.

> App chạy **local cho một người dùng, không có đăng nhập** ([ADR-004](./docs/architecture/decisions/ADR-004-single-user-first.md)). **Không deploy public.**

## Tính năng

| Nhóm | Tính năng | Màn hình |
|---|---|---|
| Ghi chép | CRUD giao dịch, nhập bằng câu tự nhiên ("ăn phở 45k"), học sở thích phân loại | `/`, `/transactions`, `/settings` |
| Ngân sách | Envelope (theo danh mục), 50/30/20, Pay Yourself First; Budget vs Actual, vùng linh hoạt 🟢🟡🔴 | `/budget`, `/budget/new` |
| Review | Review tuần / tháng (số liệu deterministic + AI diễn giải), nhìn lại chi tiêu, tư vấn điều chỉnh ngân sách | `/reviews/*`, `/budget/advice` |
| Mục tiêu & dòng tiền | Mục tiêu tiết kiệm, phân bổ PYF, khoản định kỳ, lịch + dự báo số dư | `/goals`, `/calendar` |
| Nhập liệu nhanh | Đọc hoá đơn bằng AI vision, import sao kê CSV/XLSX (mapping, dedup, phân loại hàng loạt) | `/import` |
| AI nâng cao | Financial Coach (LangGraph + tool), semantic search, RAG kiến thức có trích nguồn, mô phỏng What-if | `/coach`, `/search`, `/simulator` |
| Vận hành | Health check, lỗi `{"detail","code"}` nhất quán, nhật ký token / chi phí AI | `/settings?tab=ai-usage` |

Nguyên tắc cốt lõi ([ADR-005](./docs/architecture/decisions/ADR-005-deterministic-core-ai-layer.md)): **mọi con số do code Python tính và có unit test; AI chỉ tạo draft, diễn giải số đã tính, hoặc gọi tool chỉ đọc — không bao giờ tự ghi DB khi user chưa xác nhận.** Tiền là số nguyên đồng ([ADR-007](./docs/architecture/decisions/ADR-007-money-as-integer-vnd.md)).

## Tech stack

| Layer | Công nghệ |
|---|---|
| Frontend | Next.js 16 (App Router) + TypeScript + TailwindCSS + shadcn/ui (Base UI) + Recharts |
| Backend | FastAPI (Python 3.12+) + SQLAlchemy 2 + Alembic + Pydantic v2 |
| Database | PostgreSQL 16 + pgvector (Docker Compose) |
| AI | OpenAI API (GPT-4o / GPT-4o-mini, Vision, Embeddings), LangChain, LangGraph |
| Hạ tầng | Docker Compose (db + backend + frontend), GitHub Actions CI |

## Tài liệu

- **[docs/PROJECT-GUIDE.md](./docs/PROJECT-GUIDE.md) — giải thích toàn bộ dự án cho người mới (bảo vệ dự án)**
- [docs/demo-script.md](./docs/demo-script.md) — kịch bản demo end-to-end + smoke checklist
- [docs/README.md](./docs/README.md) — mục lục & cách bắt đầu một phase
- [docs/PROGRESS.md](./docs/PROGRESS.md) — trạng thái dự án, handoff từng phase
- [docs/architecture/](./docs/architecture/overview.md) — sơ đồ hệ thống, data model, AI architecture, ADR
- [docs/phases/](./docs/phases/) — plan chi tiết từng phase

## Biến môi trường

Backend đọc `backend/.env` (tạo từ `backend/.env.example`); frontend đọc `frontend/.env.local`.

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---|---|---|
| `DATABASE_URL` | có | `postgresql+psycopg://pfa:pfa@localhost:5433/pfa` | DB chính |
| `TEST_DATABASE_URL` | cho pytest | `…/pfa_test` | DB test (tự `alembic upgrade head`, rollback sau mỗi test) |
| `OPENAI_API_KEY` | không | — | Thiếu key: phần deterministic vẫn chạy, tính năng AI báo 503 `AI_NOT_CONFIGURED` hoặc dùng bản tự động |
| `OPENAI_MODEL_FAST` | không | `gpt-4o-mini` | Parse câu, phân loại, diễn giải advice / mô phỏng |
| `OPENAI_MODEL_SMART` | không | `gpt-4o` | Review, Coach, đọc hoá đơn |
| `OPENAI_EMBEDDING_MODEL` | không | `text-embedding-3-small` | Semantic search, RAG (1536 chiều) |
| `CORS_ORIGINS` | không | `http://localhost:3000` | Danh sách origin, phân cách bằng dấu phẩy |
| `UPLOAD_DIR` | không | `./uploads` | Ảnh hoá đơn (tính từ `backend/`) |
| `LOG_LEVEL` | không | `INFO` | |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | `http://localhost:8000/api/v1` | Trình duyệt gọi backend qua địa chỉ này |

Không commit `.env`; API key không bao giờ được log hay gửi xuống frontend.

## Chạy local (dev, khuyến nghị)

Yêu cầu: Docker Desktop (WSL2), Python 3.12+ (máy dev dùng 3.13 qua `py` launcher), Node.js 20+ (CI dùng 22), Git Bash.
Lệnh dưới đây dùng **Git Bash**, mỗi khối bắt đầu từ thư mục gốc repo.

### 1. Database (PostgreSQL 16 + pgvector)

```bash
docker compose up -d db
docker compose ps          # pfa-db phải ở trạng thái (healthy)
```

Postgres được map ra **port 5433** trên máy host (tránh đụng Postgres khác ở 5432).
Lần khởi tạo volume đầu tiên tự tạo thêm database `pfa_test` cho pytest
(script [docker/db/init](./docker/db/init/01-create-test-db.sql)).

### 2. Backend (FastAPI) — http://localhost:8000

```bash
cd backend
py -3.13 -m venv .venv            # chỉ cần lần đầu
source .venv/Scripts/activate     # venv tạo trên Windows nên là Scripts/ (thoát: deactivate)
pip install -e ".[dev]"
cp .env.example .env              # điền OPENAI_API_KEY nếu có
alembic upgrade head              # tạo bảng + seed 15 danh mục mặc định
uvicorn app.main:app --reload --port 8000
```

- Health check: `curl http://localhost:8000/api/v1/health` → `{"status","db","vector","ai_configured","version"}`
- Swagger UI: http://localhost:8000/docs
- Dữ liệu demo (xem [demo-script.md](./docs/demo-script.md)):
  - `python -m app.scripts.seed_demo --months 3 [--reset] [--seed 42] [--end YYYY-MM-DD]` — ~150 giao dịch; `--reset` xoá **mọi** giao dịch trong kỳ sinh trước khi tạo lại.
  - `python -m app.scripts.seed_scenario [--reset]` — kịch bản Budget vs Actual cố định tháng 10/2026 (ngân sách 5 danh mục + 59 giao dịch); xem ở `/budget?month=2026-10&today=2026-10-15`.
  - `python -m app.scripts.backfill_embeddings [--batch-size 100] [--limit N] [--force]` — embedding cho giao dịch seed / cũ (giao dịch tạo qua API được embed ngay). Cần key.
  - `python -m app.scripts.ingest_knowledge knowledge/ [--prune]` — ingest 6 bài kiến thức trong `backend/knowledge/` cho RAG (file không đổi được bỏ qua). Cần key.
  - `curl http://localhost:8000/api/v1/admin/smoke-data` — dữ liệu đã đủ để demo chưa.
- Nhiều màn hình nhận `?today=YYYY-MM-DD` để giả lập "hôm nay" khi demo (budget, review, coach, calendar, simulator).

### 3. Frontend (Next.js) — http://localhost:3000

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

- Lint: `npm run lint` · Type-check: `npm run typecheck` · Build production: `npm run build`
- Sinh lại type API sau khi đổi schema backend (backend phải đang chạy ở port 8000): `npm run gen:api` → `src/lib/api-types.ts` (commit file này).

## Chạy bằng Docker Compose (full stack)

```bash
docker compose up -d --build                 # db + backend + frontend
docker compose ps                            # cả 3 (healthy)
curl http://localhost:8000/api/v1/health
```

- Backend tự `alembic upgrade head` khi khởi động; đọc `backend/.env` nếu có (để lấy `OPENAI_API_KEY`), nhưng `DATABASE_URL` luôn trỏ `db:5432` trong mạng compose.
- Frontend build với `NEXT_PUBLIC_API_BASE_URL=http://localhost:${BACKEND_PORT:-8000}/api/v1` (trình duyệt gọi thẳng backend).
- Đang chạy dev server ở 8000/3000? Đổi port: `BACKEND_PORT=8001 FRONTEND_PORT=3001 docker compose up -d --build`.
- Seed trong container: `docker compose exec backend python -m app.scripts.seed_demo --months 3`.
- Dừng app, giữ DB: `docker compose rm -sf backend frontend`. Dừng tất cả: `docker compose down` (thêm `-v` sẽ **xoá dữ liệu**).

## Test

```bash
cd backend
ruff check . && ruff format --check .
pytest                                                   # ~1.190 test, không cần OpenAI key (test `ai` bị loại mặc định)
pytest --cov=app.services --cov-report=term-missing --cov-fail-under=85   # coverage lõi deterministic (hiện ~95%)
pytest -m ai                                             # golden test gọi OpenAI thật (cần OPENAI_API_KEY, tốn vài nghìn đồng)
pytest -m ai tests/ai_golden/test_coach.py -s            # một nhóm golden, in câu trả lời để đọc
```

- Pytest cần DB đang chạy; tự `alembic upgrade head` trên `pfa_test` và rollback sau mỗi test. Embedding / LLM trong test thường được fake (`tests/fake_embeddings.py`, fixture `fake_ai`, `fake_llm`).
- Golden test (`tests/ai_golden/`): NL parse, phân loại, hoá đơn (ảnh mẫu), review, advice, Coach (gồm prompt injection), import, semantic search, RAG, mô phỏng — mỗi nhóm có ngưỡng pass ghi trong docstring.
- Frontend: `cd frontend && npm run lint && npm run typecheck && npm run build`.

## CI

[.github/workflows/ci.yml](./.github/workflows/ci.yml) chạy trên push `main` và pull request:
- **backend**: Postgres `pgvector/pgvector:pg16` service → tạo `pfa_test` → `ruff check`, `ruff format --check` → `pytest --cov=app.services --cov-fail-under=85` (không cần OpenAI key).
- **frontend**: `npm ci` → `lint` → `typecheck` → `build`.

## Lưu ý khi dùng Git Bash trên Windows

- Đường dẫn có dấu cách phải đặt trong ngoặc kép: `cd "/c/Users/.../Fast Track assignment/AI-personal-finance-assistant"`.
- Mở REPL Python tương tác (gõ `python` không tham số) nếu bị treo thì dùng `winpty python`.
- Đặt biến môi trường tạm thời: `export OPENAI_API_KEY="sk-..."` (hoặc ghi vào `backend/.env`).