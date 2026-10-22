# Containers (C4 Level 2)

```mermaid
flowchart LR
    user(["Người dùng<br/>(trình duyệt)"])

    subgraph local ["Máy local / Docker Compose"]
        fe["frontend<br/>Next.js 16 + TypeScript<br/>:3000"]
        be["backend<br/>FastAPI + Uvicorn<br/>:8000"]
        db[("db<br/>PostgreSQL 16 + pgvector<br/>host :5433 → container :5432")]
        files[["uploads/<br/>ảnh hoá đơn, file import"]]
    end

    openai["OpenAI API<br/>gpt-4o-mini, gpt-4o,<br/>text-embedding-3-small"]

    user -->|"HTTPS"| fe
    fe -->|"REST JSON /api/v1<br/>(fetch, CORS localhost)"| be
    be -->|"SQLAlchemy / psycopg"| db
    be -->|"đọc/ghi"| files
    be -->|"HTTPS, openai SDK"| openai
```

## Bảng container

| Container | Công nghệ | Trách nhiệm | Có từ phase |
|---|---|---|---|
| `frontend` | Next.js (App Router), TS, Tailwind, shadcn/ui, Recharts | UI, form, dashboard, chat; không chứa business logic tài chính | 0 |
| `backend` | FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, openai, langchain, langgraph | API, business logic, AI orchestration | 0 |
| `db` | Docker image `pgvector/pgvector:pg16` | Lưu trữ; vector search | 0 (extension bật ở 15) |
| `uploads/` | Thư mục local (mount volume) | File upload | 13 |

## Cấu hình (`.env.example`)

| Biến | Dùng bởi | Ví dụ |
|---|---|---|
| `DATABASE_URL` | backend | `postgresql+psycopg://pfa:pfa@localhost:5433/pfa` |
| `TEST_DATABASE_URL` | backend (pytest) | `postgresql+psycopg://pfa:pfa@localhost:5433/pfa_test` |
| `OPENAI_API_KEY` | backend | `sk-...` |
| `OPENAI_MODEL_FAST` | backend | `gpt-4o-mini` |
| `OPENAI_MODEL_SMART` | backend | `gpt-4o` |
| `OPENAI_EMBEDDING_MODEL` | backend | `text-embedding-3-small` |
| `CORS_ORIGINS` | backend | `http://localhost:3000` |
| `UPLOAD_DIR` | backend | `./uploads` (đường dẫn tương đối tính từ thư mục `backend/`; P13 lưu ảnh hoá đơn ở `receipts/YYYY/MM/{uuid}.ext`) |
| `LOG_LEVEL` | backend | `INFO` |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | `http://localhost:8000/api/v1` |

> Port host của Postgres là **5433** (không phải 5432) để tránh xung đột với Postgres khác trên máy dev.

## Chế độ chạy local

- **Dev (khuyến nghị):** `docker compose up -d db` + chạy `uvicorn` và `npm run dev` trực tiếp trên máy để hot-reload.
- **Full compose (Phase 18):** `docker compose up -d --build` chạy cả 3 container:

| Service | Image / build | Port host | Ghi chú |
|---|---|---|---|
| `db` (`pfa-db`) | `pgvector/pgvector:pg16` | `5433` | volume `pfa_db_data`; script `docker/db/init` tạo `pfa_test` lần đầu |
| `backend` (`pfa-backend`) | `backend/Dockerfile` (python:3.13-slim, user không phải root) | `${BACKEND_PORT:-8000}` | lúc khởi động chạy `alembic upgrade head` rồi `uvicorn`; `DATABASE_URL` trỏ `db:5432`; đọc thêm `backend/.env` nếu có (không bắt buộc); volume `pfa_uploads` → `/app/uploads`; healthcheck `GET /api/v1/health` |
| `frontend` (`pfa-frontend`) | `frontend/Dockerfile` (node:22-alpine, multi-stage, `next start`) | `${FRONTEND_PORT:-3000}` | build arg `NEXT_PUBLIC_API_BASE_URL=http://localhost:${BACKEND_PORT}/api/v1` (trình duyệt gọi thẳng backend nên **không** dùng tên service nội bộ); chờ backend healthy |

> Đổi port khi máy đã chạy dev server: `BACKEND_PORT=8001 FRONTEND_PORT=3001 docker compose up -d --build` (CORS backend tự theo `FRONTEND_PORT`). Khi xong: `docker compose rm -sf backend frontend` (giữ `db`).

## CI (Phase 18)

`.github/workflows/ci.yml`: job **backend** (service `pgvector/pgvector:pg16`, tạo `pfa_test`, `ruff check` + `ruff format --check`, `pytest --cov=app.services --cov-fail-under=85` — không cần `OPENAI_API_KEY`, test `ai` bị loại mặc định) và job **frontend** (`npm ci`, `lint`, `typecheck`, `build`).
