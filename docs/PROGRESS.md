# Progress

> Cập nhật file này **mỗi khi bắt đầu và kết thúc một phase** (hoặc khi dừng giữa chừng).
> Trạng thái: `Not started` · `In progress` · `Done` · `Blocked`

## Phase hiện tại

**Tiếp theo: [Phase 5 — Budget vs Actual](./phases/phase-05-budget-vs-actual.md)** · M2 — Tracking loop hoàn chỉnh ✅

Handoff Phase 4: xem [phase-04-budget-engine.md § 9](./phases/phase-04-budget-engine.md#9-handoff-notes). Có `budgets` / `budget_allocations`, `budget_service` deterministic với 3 chiến lược (Envelope 52/12/8/20/8, 50/30/20, PYF savings trước rồi 60/30/10), preview / lưu / sửa / copy tháng trước; `/budget/new` (wizard) và `/budget` (xem/sửa/kích hoạt). Quy tắc khớp giao dịch cho Phase 5 nằm ở `budget_service.allocation_scope`: dòng danh mục → danh mục; hũ envelope → danh mục trong `budget_jar_category_map`; dòng nhóm (50/30/20, PYF) → `spending_type`. Postgres vẫn ở **port 5433**.

## Bảng trạng thái

| Phase | Tên | Trạng thái | Bắt đầu | Hoàn thành | Milestone | Ghi chú |
|---|---|---|---|---|---|---|
| D | [System design & plan export](./phases/phase-D-design-docs.md) | Done | 2026-10-07 | 2026-10-07 | | Tài liệu thiết kế + plan 20 phase |
| 0 | [Scaffolding](./phases/phase-00-scaffolding.md) | Done | 2026-10-08 | 2026-10-08 | | Next.js 16.4, shadcn base-nova, DB port 5433 |
| 1 | [Core transactions](./phases/phase-01-transactions.md) | Done | 2026-10-08 | 2026-10-08 | M1 ✅ | 93 test; summary nhận thêm filter |
| 2 | [AI natural language entry](./phases/phase-02-nl-entry.md) | Done | 2026-10-13 | 2026-10-15 | | 171 test (mock); golden 12 câu đạt 100% (prompt v2) |
| 3 | [Classification learning](./phases/phase-03-classification-learning.md) | Done | 2026-10-19 | 2026-10-19 | M2 ✅ | 259 test (mock); golden 10 bước đạt 100% |
| 4 | [Budget engine](./phases/phase-04-budget-engine.md) | Done | 2026-10-19 | 2026-10-19 | | 333 test; dòng nhóm khớp theo spending_type |
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
| 2026-10-08 | 0 | Postgres map `5433:5432`; thêm `TEST_DATABASE_URL` (DB `pfa_test`), `LOG_LEVEL` | Port 5432 trên máy dev đã bị Postgres khác chiếm; cần DB riêng cho pytest |
| 2026-10-08 | 0 | Next.js 16.4 (thay vì 15), shadcn dùng Base UI + package `cn` | Phiên bản mới nhất của `create-next-app` / shadcn CLI tại thời điểm scaffold |
| 2026-10-08 | — | Terminal chuẩn đổi từ PowerShell sang **Git Bash**: README, `copilot-instructions.md`, khối lệnh Verify của mọi phase + template dùng cú pháp bash | Người dùng dùng Git Bash làm terminal |
| 2026-10-08 | 1 | `GET /transactions/summary` nhận cùng bộ filter với list (+ `date_from/date_to`, `by_category.kind/icon`) | Thẻ tổng trên UI phải khớp bộ lọc |
| 2026-10-08 | 1 | Category expense bắt buộc `default_spending_type`; PATCH field không cho sửa → 422; không tạo/chuyển giao dịch sang category đã ẩn | Giữ dữ liệu nhất quán, lỗi rõ ràng thay vì bỏ qua âm thầm |
| 2026-10-08 | 1 | Lỗi validate trả `{"detail": [...], "code": "validation_error"}`; thêm `npm run typecheck`, `gen:api --default-non-nullable false` | Thống nhất format lỗi; type request body đúng |
| 2026-10-13 | 2 | `TransactionDraft` trả thêm `category_id`, `occurred_on` luôn có; mã lỗi AI: `AI_NOT_CONFIGURED`/`AI_AUTH_FAILED`/`AI_RATE_LIMITED`/`AI_TIMEOUT`/`AI_UNAVAILABLE` (503), `AI_INVALID_OUTPUT` (502); `422 amount_missing` | Frontend cần id để lưu; lỗi rõ ràng theo nguyên nhân |
| 2026-10-13 | 2 | Thêm `services/amount_text.extract_amounts` + lịch tham chiếu trong prompt + cảnh báo deterministic (amount/ngày) | Giảm sai số tiền/ngày, không tin hoàn toàn vào model (ADR-005) |
| 2026-10-13 | 2 | Thông báo lưu là dòng trạng thái inline thay vì toast | Repo chưa có thư viện toast |
| 2026-10-15 | 2 | Chạy golden test (trễ vì key cũ 401); prompt NL parse lên v2 (lịch mỗi ngày một dòng, đồ uống → ăn uống) | v1 đạt ngưỡng nhưng sai "thứ 7 tuần trước" và "cafe" → `other`; v2 đạt 100% |
| 2026-10-19 | 3 | `classification_preferences` unique `(user_id, pattern)` (mỗi pattern 1 preference) thay vì kèm category/type | Tránh 2 cách phân loại mâu thuẫn cho cùng từ khoá |
| 2026-10-19 | 3 | Shortcut không gọi OpenAI chỉ cho câu đơn giản (1 khoản tiền, không nêu ngày); câu khác gọi LLM rồi hậu kiểm phân loại theo preference | Ngày / nhiều khoản vẫn cần model; phần phân loại vẫn deterministic |
| 2026-10-19 | 3 | `hit_count` tăng khi user lưu draft dùng preference (không tăng lúc parse); `POST /transactions` trả `learned_preference` | Endpoint AI không ghi DB (ADR-005); UI chỉ báo "Đã học" khi backend thực sự học |
| 2026-10-19 | 3 | Prompt NL parse lên v3 (thêm mục sở thích phân loại); `/settings` dùng tabs (`?tab=`) | Few-shot preference; tab Sở thích cạnh Danh mục theo plan |
| 2026-10-19 | 4 | Dòng nhóm của 50/30/20 / PYF lưu `jar_name = group`, actual (Phase 5) khớp theo `spending_type`; service chặn phân bổ chồng lấn (`overlapping_allocations`) | Plan chưa nói dòng nhóm khớp giao dịch thế nào; tránh đếm actual 2 lần |
| 2026-10-19 | 4 | Mỗi tháng 1 budget bất kể status (409 `budget_exists`); vượt thu nhập cần `confirm_over_income`; `savings_target` = tổng nhóm savings do service tự tính; thêm `budget_allocations.position`, `GET /budgets/jars`, preview nhận `allocations` đã chỉnh | Khớp UNIQUE `period_month`; frontend không tự cộng tiền; giữ thứ tự dòng |

## Câu hỏi mở xuyên suốt

- Có cần khái niệm "tài khoản/ví" (tiền mặt, ngân hàng, thẻ tín dụng) không? Ảnh hưởng tới forecast (Phase 12) và import (Phase 14). Hiện: không.
- Chuyển khoản nội bộ / trả nợ thẻ tín dụng không phải chi tiêu — xử lý thế nào khi import (Phase 14)?
