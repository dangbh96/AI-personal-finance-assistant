# AI Personal Finance Assistant — "Personal CFO"

Trợ lý tài chính cá nhân giúp người dùng **hiểu tiền của mình đang đi đâu, lập kế hoạch sử dụng tiền, rồi định kỳ review để cải thiện hành vi tài chính**.

Core loop: **Income → Pay Yourself First → Budget → Track → Classify → Actual vs Budget → Weekly/Monthly Review → Điều chỉnh**.

## Tech stack

| Layer | Công nghệ |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + TailwindCSS + shadcn/ui + Recharts |
| Backend | FastAPI (Python 3.12+) + SQLAlchemy 2 + Alembic + Pydantic v2 |
| Database | PostgreSQL 16 + pgvector (Docker Compose) |
| AI | OpenAI API (GPT-4o / GPT-4o-mini, Vision, Embeddings), LangChain, LangGraph |

## Tài liệu

Toàn bộ thiết kế và kế hoạch theo phase nằm trong [docs/](./docs/README.md):

- [docs/README.md](./docs/README.md) — mục lục & cách bắt đầu một phase
- [docs/PROGRESS.md](./docs/PROGRESS.md) — trạng thái hiện tại của dự án
- [docs/architecture/](./docs/architecture/overview.md) — sơ đồ hệ thống
- [docs/phases/](./docs/phases/) — plan chi tiết từng phase

## Chạy local

Yêu cầu: Docker Desktop (WSL2), Python 3.12+ (máy dev dùng 3.13 qua `py` launcher), Node.js 20+.
Lệnh dưới đây dùng Windows PowerShell, chạy từ thư mục gốc repo.

### 1. Database (PostgreSQL 16 + pgvector)

```powershell
docker compose up -d db
docker compose ps          # pfa-db phải ở trạng thái (healthy)
```

Postgres được map ra **port 5433** trên máy host (tránh đụng Postgres khác ở 5432).
Lần khởi tạo volume đầu tiên tự tạo thêm database `pfa_test` cho pytest
(script [docker/db/init](./docker/db/init/01-create-test-db.sql)).

### 2. Backend (FastAPI) — http://localhost:8000

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env      # điền OPENAI_API_KEY nếu có (không bắt buộc ở Phase 0)
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- Health check: `curl http://localhost:8000/api/v1/health`
- Swagger UI: http://localhost:8000/docs
- Lint/format: `ruff check .` · `ruff format .`
- Test: `pytest` (cần DB đang chạy; không cần OpenAI key). Test gọi AI thật: `pytest -m ai`.

### 3. Frontend (Next.js) — http://localhost:3000

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

- Lint: `npm run lint` · Build: `npm run build`

Trang chủ hiển thị thẻ "Trạng thái hệ thống" (Backend / Database / AI).
