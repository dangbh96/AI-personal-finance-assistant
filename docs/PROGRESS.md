# Progress

> Cập nhật file này **mỗi khi bắt đầu và kết thúc một phase** (hoặc khi dừng giữa chừng).
> Trạng thái: `Not started` · `In progress` · `Done` · `Blocked`

## Phase hiện tại

**Tiếp theo: [Phase 0 — Scaffolding](./phases/phase-00-scaffolding.md)**

## Bảng trạng thái

| Phase | Tên | Trạng thái | Bắt đầu | Hoàn thành | Milestone | Ghi chú |
|---|---|---|---|---|---|---|
| D | [System design & plan export](./phases/phase-D-design-docs.md) | Done | 2026-10-07 | 2026-10-07 | | Tài liệu thiết kế + plan 20 phase |
| 0 | [Scaffolding](./phases/phase-00-scaffolding.md) | Not started | | | | |
| 1 | [Core transactions](./phases/phase-01-transactions.md) | Not started | | | M1 | |
| 2 | [AI natural language entry](./phases/phase-02-nl-entry.md) | Not started | | | | |
| 3 | [Classification learning](./phases/phase-03-classification-learning.md) | Not started | | | M2 | |
| 4 | [Budget engine](./phases/phase-04-budget-engine.md) | Not started | | | | |
| 5 | [Budget vs Actual](./phases/phase-05-budget-vs-actual.md) | Not started | | | M3 | |
| 6 | [Weekly review](./phases/phase-06-weekly-review.md) | Not started | | | | |
| 7 | [Monthly review](./phases/phase-07-monthly-review.md) | Not started | | | M4 (MVP) | |
| 8 | [Budget adjustment advisor](./phases/phase-08-budget-advisor.md) | Not started | | | | |
| 9 | [Flexible budget zones](./phases/phase-09-flexible-zones.md) | Not started | | | | |
| 10 | [Financial Coach](./phases/phase-10-financial-coach.md) | Not started | | | M5 | |
| 11 | [Goals + Pay Yourself First](./phases/phase-11-goals-pyf.md) | Not started | | | | |
| 12 | [Calendar & cashflow forecast](./phases/phase-12-calendar-forecast.md) | Not started | | | | |
| 13 | [Receipt OCR](./phases/phase-13-receipt-ocr.md) | Not started | | | | |
| 14 | [CSV / Excel import](./phases/phase-14-csv-import.md) | Not started | | | | |
| 15 | [Semantic search](./phases/phase-15-semantic-search.md) | Not started | | | | |
| 16 | [RAG knowledge base](./phases/phase-16-rag-knowledge.md) | Not started | | | M6 | |
| 17 | [What-if simulator](./phases/phase-17-whatif-simulator.md) | Not started | | | | Stretch |
| 18 | [Hardening & wrap-up](./phases/phase-18-hardening.md) | Not started | | | M7 | |

## Milestones

| ID | Ý nghĩa | Đạt sau phase |
|---|---|---|
| M1 | Ghi chép thủ công dùng được | 1 |
| M2 | Tracking loop hoàn chỉnh (nhập NL + AI học phân loại) | 3 |
| M3 | Budget loop hoàn chỉnh | 5 |
| M4 | Review loop — **MVP sản phẩm** | 7 |
| M5 | AI Agent (Financial Coach) | 10 |
| M6 | Full AI curriculum (Vision, Embeddings, RAG) | 16 |
| M7 | Hoàn thiện | 18 |

## Change log (thay đổi so với plan)

| Ngày | Phase | Thay đổi | Lý do |
|---|---|---|---|
| 2026-10-07 | D | Thêm `frontend-structure.md`, ADR-007 (tiền là số nguyên đồng) | Cần cho tính nhất quán giữa các phase |

## Câu hỏi mở xuyên suốt

- Có cần khái niệm "tài khoản/ví" (tiền mặt, ngân hàng, thẻ tín dụng) không? Ảnh hưởng tới forecast (Phase 12) và import (Phase 14). Hiện: không.
- Chuyển khoản nội bộ / trả nợ thẻ tín dụng không phải chi tiêu — xử lý thế nào khi import (Phase 14)?
