# Containers (C4 Level 2)

```mermaid
flowchart LR
    user(["Người dùng<br/>(trình duyệt)"])

    subgraph local ["Máy local / Docker Compose"]
        fe["frontend<br/>Next.js 15 + TypeScript<br/>:3000"]
        be["backend<br/>FastAPI + Uvicorn<br/>:8000"]
        db[("db<br/>PostgreSQL 16 + pgvector<br/>:5432")]
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
| `DATABASE_URL` | backend | `postgresql+psycopg://pfa:pfa@localhost:5432/pfa` |
| `OPENAI_API_KEY` | backend | `sk-...` |
| `OPENAI_MODEL_FAST` | backend | `gpt-4o-mini` |
| `OPENAI_MODEL_SMART` | backend | `gpt-4o` |
| `OPENAI_EMBEDDING_MODEL` | backend | `text-embedding-3-small` |
| `CORS_ORIGINS` | backend | `http://localhost:3000` |
| `UPLOAD_DIR` | backend | `./uploads` |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | `http://localhost:8000/api/v1` |

## Chế độ chạy local

- **Dev (khuyến nghị):** `docker compose up -d db` + chạy `uvicorn` và `npm run dev` trực tiếp trên máy để hot-reload.
- **Full compose (tuỳ chọn, Phase 18):** cả 3 container trong `docker compose up`.
