# Phase 01 — Core Transaction Management

| | |
|---|---|
| **ID** | `phase-01-transactions` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 0 |
| **Mở khoá** | Phase 2, 4, 15 |
| **Milestone** | **M1 — Ghi chép thủ công dùng được** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 0](./phase-00-scaffolding.md)
2. [glossary.md](../product/glossary.md) — `direction`, `spending_type`, danh mục mặc định
3. [data-model.md](../architecture/data-model.md) — entity `CATEGORY`, `TRANSACTION`, `APP_SETTING`, ràng buộc
4. [backend-components.md](../architecture/backend-components.md) — quy tắc phụ thuộc, API conventions
5. [frontend-structure.md](../architecture/frontend-structure.md) — route `/transactions`, `/settings`
6. [ADR-007](../architecture/decisions/ADR-007-money-as-integer-vnd.md) — tiền là số nguyên đồng

Trạng thái code giả định: khung Phase 0 chạy được, Alembic có migration baseline.

## 2. Mục tiêu & giá trị cho user

User ghi được thu nhập và chi tiêu thủ công với phân loại 2 chiều (Category × Spending type), xem lại, sửa, xoá, lọc theo tháng. Đây là nền móng dữ liệu cho mọi phase sau.

## 3. Scope

**In scope**
- Bảng `categories`, `transactions`, `app_settings` + migration + seed 15 danh mục mặc định (theo glossary).
- Cột `raw_input`, `ai_suggestion`, `source` tạo luôn ở phase này (nullable) để Phase 2 không cần migrate lại.
- CRUD API transactions + categories, filter, phân trang, tổng thu/chi theo khoảng thời gian.
- `services/money.py` với `round_vnd()` và helper kỳ (`month_range`, `week_range` — tuần bắt đầu Thứ Hai).
- Script seed dữ liệu demo (`python -m app.scripts.seed_demo --months 3`) — sinh giao dịch ngẫu nhiên có quy luật, dùng cho Phase 5–9.
- Sinh TypeScript types từ OpenAPI (`openapi-typescript`) → `frontend/src/lib/api-types.ts`.
- UI `/transactions` (bảng + form + filter) và `/settings` (quản lý category).

**Out of scope**
- Nhập bằng câu tự nhiên (Phase 2), import file (Phase 14), recurring (Phase 12).
- Xoá category đang được dùng (chỉ cho "ẩn" — `is_archived`).

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`categories`: `id`, `name`, `slug` (unique), `kind` (`income|expense`), `default_spending_type` (nullable), `icon`, `is_system`, `is_archived`, timestamps.

`transactions`: `id`, `user_id` (nullable), `direction`, `amount BIGINT CHECK (amount > 0)`, `occurred_on DATE`, `note TEXT`, `category_id FK`, `spending_type` (nullable), `source DEFAULT 'manual'`, `raw_input`, `ai_suggestion JSONB`, timestamps.
- CHECK: `(direction='income' AND spending_type IS NULL) OR (direction='expense' AND spending_type IS NOT NULL)`.
- CHECK: `category.kind` khớp `direction` → validate ở service (không làm cross-table CHECK).
- Index: `(occurred_on)`, `(category_id, occurred_on)`.

`app_settings`: `key TEXT PK`, `value JSONB` — seed `{"week_start": "monday", "currency": "VND"}`.

### 4.2 Backend

| Method | Path | Mô tả | Ghi chú |
|---|---|---|---|
| GET | `/api/v1/categories` | Danh sách | `?kind=expense&include_archived=false` |
| POST | `/api/v1/categories` | Tạo category tuỳ chỉnh | slug tự sinh từ name (bỏ dấu) |
| PATCH | `/api/v1/categories/{id}` | Sửa name/icon/default_spending_type/is_archived | Không sửa `is_system` |
| GET | `/api/v1/transactions` | Danh sách | `?from=&to=&category_id=&spending_type=&direction=&q=&page=&page_size=`; sort `occurred_on desc` |
| POST | `/api/v1/transactions` | Tạo | Validate direction ↔ category.kind ↔ spending_type; nếu expense thiếu `spending_type` → dùng `category.default_spending_type` |
| GET | `/api/v1/transactions/{id}` | Chi tiết | |
| PATCH | `/api/v1/transactions/{id}` | Sửa | |
| DELETE | `/api/v1/transactions/{id}` | Xoá | 204 |
| GET | `/api/v1/transactions/summary` | Tổng hợp | `?from=&to=` → `{income_total, expense_total, net, by_spending_type:{essential,non_essential,irregular}, by_category:[{category_id,name,total}]}` |

`services/transaction_service.py` chứa validate + summary (SQL aggregate). Router mỏng.

### 4.3 AI
Không có.

### 4.4 Frontend
- `/transactions`: filter bar (chọn tháng, category, spending type, direction, ô tìm note), `TransactionTable` (ngày, note, category, badge spending type màu, số tiền xanh/đỏ), thẻ tổng thu/chi/net của bộ lọc, nút "Thêm giao dịch" mở `TransactionForm` (dialog).
- `TransactionForm`: toggle Thu/Chi → danh sách category lọc theo kind → spending type (ẩn khi Thu, tự điền default khi chọn category) → amount (input hỗ trợ gõ `55k`, `1tr5` bằng parser đơn giản phía client — chỉ là tiện ích, backend vẫn nhận số nguyên) → ngày (mặc định hôm nay) → note.
- Sửa/xoá từ dòng trong bảng (xoá có confirm).
- `/settings`: bảng category, thêm/sửa/ẩn.
- `src/lib/format.ts`: `formatVND`.

## 5. Task breakdown

- [ ] T1 ORM models + Alembic migration + seed categories (migration data hoặc script idempotent)
- [ ] T2 `services/money.py` (`round_vnd`, `month_range`, `week_range`) + unit test
- [ ] T3 Pydantic schemas (create/update/read) + `transaction_service` validate
- [ ] T4 Routers categories + transactions CRUD + filter/pagination
- [ ] T5 `GET /transactions/summary` + test số liệu
- [ ] T6 Test API (pytest, DB test riêng, rollback mỗi test)
- [ ] T7 Script `seed_demo` (3 tháng, ~150 giao dịch: lương ngày 5, tiền nhà ngày 1, ăn uống hằng ngày, vài khoản irregular)
- [ ] T8 Sinh `api-types.ts` từ `/openapi.json` (script `npm run gen:api`)
- [ ] T9 UI `/transactions` (bảng, filter, summary cards)
- [ ] T10 UI `TransactionForm` tạo/sửa + xoá
- [ ] T11 UI `/settings` categories
- [ ] T12 Cập nhật docs nếu lệch, PROGRESS, handoff, commit

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend && alembic upgrade head && ruff check . && pytest
python -m app.scripts.seed_demo --months 3
cd ../frontend && npm run gen:api && npm run lint && npm run dev
```

**Test cases (pytest)**
| # | Input | Kỳ vọng |
|---|---|---|
| 1 | POST expense 55000, category food, không gửi spending_type | 201, `spending_type = essential` (default của food) |
| 2 | POST income 25000000, category salary, spending_type `essential` | 422 (income không có spending_type) |
| 3 | POST expense với category `salary` | 422 (kind không khớp) |
| 4 | POST amount 0 hoặc âm | 422 |
| 5 | 3 giao dịch tháng 9 + 1 tháng 10, GET `?from=2026-09-01&to=2026-09-30` | đúng 3 dòng |
| 6 | `/summary` với dữ liệu biết trước | tổng income/expense/by_spending_type khớp tính tay |
| 7 | `week_range(2026-10-07)` | `2026-10-05` → `2026-10-11` |
| 8 | PATCH category `is_system` | 422 / bị bỏ qua |

**Kịch bản UI**
1. Thêm "Ăn phở 55.000, Ăn uống, Thiết yếu" → xuất hiện đầu bảng, tổng chi tăng 55.000.
2. Thêm thu nhập Lương 25.000.000 → ô spending type bị ẩn; tổng thu cập nhật.
3. Sửa giao dịch phở thành 60.000 → bảng + tổng cập nhật.
4. Lọc spending type "Không thiết yếu" → chỉ còn dòng tương ứng.
5. Xoá 1 giao dịch → có confirm, biến mất.
6. Tạo category "Thú cưng" (expense, non_essential) → dùng được trong form.

## 7. Definition of Done

- [ ] Tất cả task + verify pass; `ruff`, `pytest`, `npm run lint` xanh
- [ ] [data-model.md](../architecture/data-model.md) khớp schema thực tế
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật (đánh dấu M1), Handoff notes điền
- [ ] Commit `phase-01: ...`

## 8. Rủi ro / câu hỏi mở

- Tìm kiếm note tiếng Việt có dấu/không dấu: Phase 1 dùng `ILIKE` đơn giản; có thể thêm extension `unaccent` nếu cần.
- Có cần "tài khoản/ví" (tiền mặt, ngân hàng, thẻ) không? Hiện **không** — ghi nhận như ý tưởng mở rộng.
- Chuyển tiền giữa ví / trả nợ thẻ tín dụng không phải chi tiêu — hiện ngoài phạm vi.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
