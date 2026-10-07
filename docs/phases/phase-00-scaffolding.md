# Phase 00 — Project Scaffolding & Dev Environment

| | |
|---|---|
| **ID** | `phase-00-scaffolding` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase D |
| **Mở khoá** | Phase 1 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md)
2. [architecture/overview.md](../architecture/overview.md) — cấu trúc repo đích
3. [architecture/containers.md](../architecture/containers.md) — container, port, biến môi trường
4. [architecture/backend-components.md](../architecture/backend-components.md) — module + quy tắc phụ thuộc
5. [architecture/frontend-structure.md](../architecture/frontend-structure.md)
6. ADR [001](../architecture/decisions/ADR-001-fastapi-nextjs.md), [002](../architecture/decisions/ADR-002-postgres-pgvector.md)

Trạng thái code khi bắt đầu: repo chỉ có `docs/`, `README.md`, `.gitignore`, `.github/copilot-instructions.md`.

## 2. Mục tiêu & giá trị cho user

Một bộ khung chạy được end-to-end (Frontend → Backend → DB) để mọi phase sau chỉ việc thêm tính năng. Chưa có giá trị nghiệp vụ.

## 3. Scope

**In scope**
- `docker-compose.yml` với service `db` (image `pgvector/pgvector:pg16`, volume dữ liệu, healthcheck).
- `backend/`: FastAPI app, cấu hình bằng `pydantic-settings`, SQLAlchemy engine/session, Alembic init (chưa có bảng nghiệp vụ), `GET /api/v1/health` kiểm tra kết nối DB, CORS, logging cơ bản, pytest + 1 test.
- Khung thư mục rỗng theo [overview.md](../architecture/overview.md): `core/ models/ schemas/ repositories/ services/ ai/ agents/ api/routers/`.
- `ai/openai_client.py` khung: đọc key/model từ env, hàm `is_configured()`; **chưa** gọi API thật (để Phase 2).
- Công cụ chất lượng: `ruff` (lint + format), cấu hình trong `pyproject.toml`.
- `frontend/`: Next.js (App Router, TS), Tailwind, shadcn/ui init, `src/lib/api.ts`, trang `/` hiển thị trạng thái backend + DB.
- `.env.example` (root hoặc `backend/.env.example` + `frontend/.env.local.example`).
- Cập nhật `README.md` phần "Chạy local".

**Out of scope**
- Bảng nghiệp vụ (Phase 1).
- Gọi OpenAI thật (Phase 2).
- Docker hoá backend/frontend (Phase 18).
- CI pipeline (Phase 18).

## 4. Thiết kế chi tiết

### 4.1 Data model / migration
- Alembic migration đầu tiên **rỗng** (baseline) để xác nhận pipeline migration chạy được.
- Chưa bật extension `vector` (Phase 15) — nhưng image đã hỗ trợ sẵn.

### 4.2 Backend

Dependency chính (`pyproject.toml`, quản lý bằng `uv` hoặc `pip` + venv): `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `psycopg[binary]`, `alembic`, `pydantic-settings`, `openai`; dev: `pytest`, `httpx`, `ruff`.

| Method | Path | Mô tả | Response |
|---|---|---|---|
| GET | `/api/v1/health` | Kiểm tra app + DB (`SELECT 1`) | `{"status":"ok","db":"ok","ai_configured":true\|false,"version":"0.0.1"}`; nếu DB lỗi: HTTP 503 `{"status":"degraded","db":"error"}` |

File chính:
- `app/main.py` — tạo app, CORS từ `CORS_ORIGINS`, include router `/api/v1`.
- `app/core/config.py` — `Settings` (DATABASE_URL, OPENAI_*, CORS_ORIGINS, UPLOAD_DIR).
- `app/core/db.py` — engine, `SessionLocal`, dependency `get_db`.
- `app/api/routers/health.py`.

Test: dùng một database test riêng (`pfa_test`) hoặc override `get_db`; Phase 0 chỉ cần test health với DB thật đang chạy qua compose.

### 4.3 AI
Không có. Chỉ khung `openai_client.is_configured()`.

### 4.4 Frontend
- `create-next-app` (TS, App Router, Tailwind, ESLint, `src/`).
- `npx shadcn@latest init`, thêm component `card`, `badge`, `button`.
- `src/lib/api.ts`: `apiGet<T>(path)` dùng `NEXT_PUBLIC_API_BASE_URL`.
- `src/app/page.tsx`: card "Trạng thái hệ thống": Backend OK/Lỗi, DB OK/Lỗi, AI đã cấu hình/chưa.
- Layout cơ bản: header tên app, sidebar/nav placeholder cho các route tương lai.

## 5. Task breakdown

- [ ] T1 `docker-compose.yml` service `db` + healthcheck; `docker compose up -d db` chạy được
- [ ] T2 Khởi tạo `backend/` (venv, `pyproject.toml`, cấu trúc thư mục, ruff)
- [ ] T3 `config.py`, `db.py`, `main.py`, router health
- [ ] T4 Alembic init + migration baseline rỗng, `alembic upgrade head` chạy được
- [ ] T5 pytest: test health trả 200 khi DB lên
- [ ] T6 Khởi tạo `frontend/` (Next.js + Tailwind + shadcn)
- [ ] T7 `api.ts` + trang chủ hiển thị trạng thái
- [ ] T8 `.env.example` + README "Chạy local" (Windows PowerShell commands)
- [ ] T9 Commit `phase-00: scaffolding`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
docker compose up -d db
docker compose ps                      # db healthy

cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1   # máy này: dùng `py -3.13 -m venv .venv` (lệnh `python` chưa có trong PATH)
pip install -e ".[dev]"
alembic upgrade head
ruff check .
pytest
uvicorn app.main:app --reload --port 8000
# terminal khác:
curl http://localhost:8000/api/v1/health

cd frontend
npm install
npm run lint
npm run dev                           # mở http://localhost:3000
```

**Test cases**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1 | DB đang chạy, GET `/api/v1/health` | 200, `db: "ok"` |
| 2 | `docker compose stop db`, GET health | 503, `db: "error"` (không crash) |
| 3 | Không có `OPENAI_API_KEY` | `ai_configured: false`, app vẫn chạy |
| 4 | `http://localhost:8000/docs` | Swagger UI hiển thị endpoint health |

**Kịch bản UI**
1. Mở `http://localhost:3000` → thấy "Backend: OK", "Database: OK".
2. Tắt backend → refresh → thấy "Backend: không kết nối được" (không trắng trang).

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `ruff check`, `pytest`, `npm run lint` xanh
- [ ] README có hướng dẫn chạy local đúng thực tế
- [ ] Nếu đổi port/biến môi trường → cập nhật [containers.md](../architecture/containers.md)
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-00: ...`

## 8. Rủi ro / câu hỏi mở

- Docker Desktop trên Windows cần WSL2; nếu không có Docker, phương án dự phòng: cài PostgreSQL 16 + pgvector native.
- Máy dev hiện có Python 3.13 qua `py` launcher, `python` không có trong PATH → tạo venv bằng `py -3.13 -m venv .venv`; sau khi activate venv thì `python` dùng bình thường. Kiểm tra mọi dependency (đặc biệt `psycopg[binary]`, `langgraph`) có wheel cho 3.13; nếu không, cài Python 3.12.
- Port 5432 có thể đã bị Postgres khác chiếm → map `5433:5432` và cập nhật `DATABASE_URL`.
- Version Next.js/shadcn thay đổi nhanh — ghi version thực tế đã dùng vào Handoff notes.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
