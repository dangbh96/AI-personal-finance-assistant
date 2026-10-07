# Documentation Index

Tài liệu là **nguồn sự thật** của dự án. Code phải khớp tài liệu; nếu thực tế khác thiết kế thì cập nhật tài liệu trong cùng commit.

## Bắt đầu nhanh

| Bạn muốn… | Đọc |
|---|---|
| Biết dự án đang ở đâu | [PROGRESS.md](./PROGRESS.md) |
| Hiểu sản phẩm làm gì | [product/vision.md](./product/vision.md) |
| Biết tên gọi chuẩn trong code | [product/glossary.md](./product/glossary.md) |
| Hiểu kiến trúc | [architecture/overview.md](./architecture/overview.md) |
| Xem thứ tự các phase | [architecture/phase-roadmap.md](./architecture/phase-roadmap.md) |
| Làm phase tiếp theo | file tương ứng trong [phases/](./phases/) |

## Quy trình làm một phase (mỗi session / mỗi ngày)

1. Mở [PROGRESS.md](./PROGRESS.md) → xác định phase hiện tại, đọc **Handoff notes** của phase vừa xong.
2. Mở file phase trong [phases/](./phases/) → đọc mục **1. Context cần đọc trước** và đọc các link đó.
3. Đổi trạng thái phase thành `In progress` trong PROGRESS.md.
4. Nếu thấy plan của phase không còn hợp lý → sửa file phase **trước** khi code, ghi lý do vào Change log của PROGRESS.md.
5. Làm lần lượt các task ở mục **5**, tick `[x]` khi xong. Commit nhỏ, thường xuyên (`phase-XX: <mô tả>`).
6. Chạy toàn bộ mục **6. Verify**. Chưa pass thì chưa sang phase sau.
7. Kiểm tra **7. Definition of Done**, điền **9. Handoff notes**.
8. Cập nhật PROGRESS.md (trạng thái `Done`, ngày, ghi chú) và sơ đồ/ERD nếu thiết kế thay đổi.
9. Commit cuối phase.

Nếu một session kết thúc giữa chừng: ghi trạng thái dở dang vào Handoff notes (mục "Đã làm" + "TODO để lại") và PROGRESS.md trước khi dừng.

## Cấu trúc thư mục

```
docs/
├── README.md                     ← bạn đang ở đây
├── PROGRESS.md                   ← trạng thái + change log
├── product/
│   ├── vision.md                 ← tầm nhìn, nguyên tắc, phạm vi
│   ├── glossary.md               ← thuật ngữ VN ↔ EN ↔ code
│   ├── feature-map.md            ← feature → công nghệ → phase
│   └── brainstorm-original.md    ← bản brainstorm gốc (read-only)
├── architecture/
│   ├── overview.md
│   ├── system-context.md         ← C4 L1
│   ├── containers.md             ← C4 L2 + env vars
│   ├── backend-components.md     ← module + quy tắc phụ thuộc + API conventions
│   ├── frontend-structure.md     ← route/màn hình
│   ├── data-model.md             ← ERD + bảng theo phase
│   ├── core-loop.md              ← business loop
│   ├── ai-architecture.md        ← tác vụ AI, LangGraph, guardrails, golden tests
│   ├── sequences.md              ← sequence diagrams
│   ├── budget-adjustment.md      ← advisor decision tree + flexible zones
│   ├── phase-roadmap.md          ← phụ thuộc giữa các phase
│   └── decisions/                ← ADR-001 … ADR-007
└── phases/
    ├── _TEMPLATE.md
    ├── phase-D-design-docs.md
    ├── phase-00-scaffolding.md
    ├── …
    └── phase-18-hardening.md
```

## Danh sách phase

| Phase | File |
|---|---|
| D | [System design & plan export](./phases/phase-D-design-docs.md) |
| 0 | [Scaffolding](./phases/phase-00-scaffolding.md) |
| 1 | [Core transactions](./phases/phase-01-transactions.md) |
| 2 | [AI natural language entry](./phases/phase-02-nl-entry.md) |
| 3 | [Classification learning](./phases/phase-03-classification-learning.md) |
| 4 | [Budget engine](./phases/phase-04-budget-engine.md) |
| 5 | [Budget vs Actual](./phases/phase-05-budget-vs-actual.md) |
| 6 | [Weekly review](./phases/phase-06-weekly-review.md) |
| 7 | [Monthly review](./phases/phase-07-monthly-review.md) |
| 8 | [Budget adjustment advisor](./phases/phase-08-budget-advisor.md) |
| 9 | [Flexible budget zones](./phases/phase-09-flexible-zones.md) |
| 10 | [Financial Coach](./phases/phase-10-financial-coach.md) |
| 11 | [Goals + Pay Yourself First](./phases/phase-11-goals-pyf.md) |
| 12 | [Calendar & cashflow forecast](./phases/phase-12-calendar-forecast.md) |
| 13 | [Receipt OCR](./phases/phase-13-receipt-ocr.md) |
| 14 | [CSV / Excel import](./phases/phase-14-csv-import.md) |
| 15 | [Semantic search](./phases/phase-15-semantic-search.md) |
| 16 | [RAG knowledge base](./phases/phase-16-rag-knowledge.md) |
| 17 | [What-if simulator](./phases/phase-17-whatif-simulator.md) |
| 18 | [Hardening & wrap-up](./phases/phase-18-hardening.md) |

## Xem sơ đồ Mermaid

- GitHub render Mermaid tự động.
- VS Code: Markdown Preview (`Ctrl+Shift+V`); nếu không render, cài extension **Markdown Preview Mermaid Support** (`bierner.markdown-mermaid`).
