# Phase 01 — Core Transaction Management

| | |
|---|---|
| **ID** | `phase-01-transactions` |
| **Trạng thái** | Done |
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

- [x] T1 ORM models + Alembic migration + seed categories (migration data hoặc script idempotent)
- [x] T2 `services/money.py` (`round_vnd`, `month_range`, `week_range`) + unit test
- [x] T3 Pydantic schemas (create/update/read) + `transaction_service` validate
- [x] T4 Routers categories + transactions CRUD + filter/pagination
- [x] T5 `GET /transactions/summary` + test số liệu
- [x] T6 Test API (pytest, DB test riêng, rollback mỗi test)
- [x] T7 Script `seed_demo` (3 tháng, ~150 giao dịch: lương ngày 5, tiền nhà ngày 1, ăn uống hằng ngày, vài khoản irregular)
- [x] T8 Sinh `api-types.ts` từ `/openapi.json` (script `npm run gen:api`)
- [x] T9 UI `/transactions` (bảng, filter, summary cards)
- [x] T10 UI `TransactionForm` tạo/sửa + xoá
- [x] T11 UI `/settings` categories
- [x] T12 Cập nhật docs nếu lệch, PROGRESS, handoff, commit

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

- [x] Tất cả task + verify pass; `ruff`, `pytest`, `npm run lint` xanh
- [x] [data-model.md](../architecture/data-model.md) khớp schema thực tế
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật (đánh dấu M1), Handoff notes điền
- [x] Commit `phase-01: ...`

## 8. Rủi ro / câu hỏi mở

- Tìm kiếm note tiếng Việt có dấu/không dấu: Phase 1 dùng `ILIKE` đơn giản; có thể thêm extension `unaccent` nếu cần.
- Có cần "tài khoản/ví" (tiền mặt, ngân hàng, thẻ) không? Hiện **không** — ghi nhận như ý tưởng mở rộng.
- Chuyển tiền giữa ví / trả nợ thẻ tín dụng không phải chi tiêu — hiện ngoài phạm vi.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-08
- **Đã làm:**
  - **DB** (migration `20261008_ac3898ef679d_core_transactions`): `categories`, `transactions`, `app_settings` + CHECK constraints + 2 index; seed 15 danh mục (có emoji `icon`, `is_system=true`) và `app_settings` (`week_start`, `currency`) ngay trong migration. `Base.metadata` có naming convention (`app/core/db.py`). Đã thử `upgrade → downgrade -1 → upgrade`.
  - **Backend:** `models/{category,transaction,app_setting,enums,mixins}.py`; `repositories/{category,transaction}_repository.py` (filter, phân trang, aggregate SQL); `services/money.py` (`round_vnd` làm tròn nửa ra xa 0, `month_range`, `week_range` tuần từ Thứ Hai, `add_months`), `services/category_service.py`, `services/transaction_service.py` (validate direction ↔ category.kind ↔ spending_type, fallback `default_spending_type`, `summarize`); routers `categories`, `transactions` (đúng bảng API mục 4.2); `core/errors.py` (`DomainError`/`NotFoundError` → `{"detail","code"}`); `core/text.py` (`strip_accents`, `slugify`).
  - **Test (93 pass):** `tests/conftest.py` chạy `alembic upgrade head` trên `pfa_test` 1 lần/session, mỗi test 1 connection + SAVEPOINT (`join_transaction_mode="create_savepoint"`) rồi rollback → test ghi dữ liệu thoải mái. Đủ 8 test case mục 6 + PATCH semantics, archived category, phân trang, escape `%`/`_` khi tìm, CHECK DB, `seed_demo.generate`.
  - **Seed demo:** `python -m app.scripts.seed_demo --months 3` → N tháng trọn + tháng hiện tại tới hôm nay (seed 42: 156 giao dịch cho 3 tháng trọn, 174 tính cả 8 ngày tháng 10). Đi qua `transaction_service` nên dữ liệu hợp lệ như nhập tay. DB dev hiện đã có dữ liệu này.
  - **Frontend:** `npm run gen:api` → `src/lib/api-types.ts`; `src/lib/api.ts` (`apiRequest`, `withQuery`, `describeError`, type alias từ OpenAPI); `src/hooks/use-api-data.ts`; `src/lib/{format,dates,amount,labels}.ts`; `/transactions` (`TransactionsView`, `TransactionFilters`, `TransactionTable`, `TransactionSummaryCards`, `TransactionFormDialog`, `DeleteTransactionDialog`), `/settings` (`CategoryManager`, `CategoryFormDialog`); `AppNav` thành client component, highlight route hiện tại. shadcn thêm `dialog alert-dialog input label select table textarea`.
  - **Verify:** `ruff check`, `ruff format --check`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` đều xanh; 6 kịch bản UI đã chạy trên trình duyệt (kèm: lỗi validate form, danh mục bị ẩn không xuất hiện khi tạo mới nhưng vẫn giữ khi sửa giao dịch cũ).
- **Lệch so với plan (và lý do):**
  - `GET /transactions/summary` nhận **thêm** các filter như list (`category_id`, `spending_type`, `direction`, `q`) và trả thêm `date_from`, `date_to`; `by_category` có thêm `kind`, `icon` → thẻ tổng của UI phản ánh đúng bộ lọc.
  - Category expense **bắt buộc** `default_spending_type` (tạo và PATCH) để giao dịch chi luôn tự điền được loại chi tiêu.
  - PATCH category gửi `is_system`/`kind`/`slug` → **422** (`extra="forbid"`), không âm thầm bỏ qua. Tương tự PATCH transaction không sửa `source`/`raw_input`/`ai_suggestion`.
  - PATCH transaction đổi category mà không gửi `spending_type` → lấy default của category mới; không đổi category → giữ `spending_type` cũ.
  - Không cho tạo giao dịch / chuyển giao dịch sang category đã ẩn (`code: category_archived`).
  - Thêm `services/money.add_months`, `transaction_service.delete_transactions_in_range` (cho `seed_demo --reset`), `category_service.get_category_by_slug`.
  - Ruff: thêm `[tool.ruff.lint.isort] known-third-party = ["alembic"]` (thư mục `alembic/` làm ruff tưởng là first-party). `alembic/env.py` chỉ đặt URL nếu caller chưa đặt và bỏ `fileConfig` khi `config.attributes["configure_logger"] = False` (dùng trong conftest).
  - `gen:api` dùng `--default-non-nullable false` (mặc định openapi-typescript coi field có default là bắt buộc → sai cho request body).
  - Không đưa filter vào URL (state client) — đơn giản, tránh `useSearchParams` + Suspense; có thể làm sau nếu cần chia sẻ link.
- **Nợ kỹ thuật / TODO để lại:**
  - Tìm kiếm note dùng `ILIKE` (phân biệt dấu: "pho" không khớp "phở"). Cân nhắc `unaccent` hoặc cột note chuẩn hoá (Phase 3/15 có thể dùng `core/text.strip_accents`).
  - Chưa có test tự động cho frontend (parser `parseAmountInput` mới kiểm tra ad-hoc bằng Node). Nên thêm Vitest ở Phase 18.
  - `seed_demo` không đánh dấu dữ liệu demo; `--reset` xoá mọi giao dịch trong kỳ.
  - Viewport hẹp (< ~900px) bảng giao dịch cuộn ngang trong khung bảng; sidebar ẩn dưới `md` nhưng chưa có menu mobile.
- **Lệnh hữu ích:**
  - `cd backend && python -m app.scripts.seed_demo --months 3 --reset`
  - `cd frontend && npm run gen:api` (backend đang chạy) · `npm run typecheck` · `npm run build`
  - `docker exec -it pfa-db psql -U pfa -d pfa -c "select to_char(occurred_on,'YYYY-MM'), count(*) from transactions group by 1 order by 1;"`
- **Gợi ý cho phase tiếp theo (Phase 2 — NL entry):**
  - AI parser chỉ trả draft `TransactionCreate` (có `source="nl"`, `raw_input`, `ai_suggestion`); user xác nhận rồi gọi `POST /transactions` như cũ — không cần migration.
  - Có thể dùng chung bảng quy đổi gõ tắt ở `src/lib/amount.ts` làm few-shot / fallback deterministic cho số tiền.
  - Context danh mục cho prompt: `GET /categories?kind=...` hoặc `category_service.list_categories`.
  - `TransactionForm` hiện khởi tạo state từ `transaction` (và PATCH khi có `transaction`) → để hiển thị draft AI cho user sửa, tách thêm prop `initialValues` (prefill nhưng vẫn POST).
