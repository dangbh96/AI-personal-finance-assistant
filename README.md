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

Chưa có code ứng dụng. Hướng dẫn chạy sẽ được bổ sung ở [Phase 0](./docs/phases/phase-00-scaffolding.md).
