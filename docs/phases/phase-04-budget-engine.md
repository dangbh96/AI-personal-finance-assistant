# Phase 04 — Budget Engine

| | |
|---|---|
| **ID** | `phase-04-budget-engine` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 1 |
| **Mở khoá** | Phase 5, 11 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 1](./phase-01-transactions.md)
2. [glossary.md](../product/glossary.md) — `Budget`, `BudgetAllocation`, strategy, group, jar
3. [vision.md](../product/vision.md) — không ép một phương pháp budget; 50/30/20 là tham khảo
4. [data-model.md](../architecture/data-model.md) — `budgets`, `budget_allocations`, period_month, money BIGINT
5. [core-loop.md](../architecture/core-loop.md) — income → PYF → budget → track
6. [backend-components.md](../architecture/backend-components.md) — `budget_service` deterministic, services không gọi AI
7. [frontend-structure.md](../architecture/frontend-structure.md) — `/budget/new`
8. [phase-roadmap.md](../architecture/phase-roadmap.md) — Phase 4 mở khoá Phase 5 và 11
9. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu: Phase 1 Done; có categories mặc định, transaction CRUD, `services/money.py` với `round_vnd`; chưa có bảng budget.

## 2. Mục tiêu & giá trị cho user

User tạo ngân sách tháng theo một trong ba chiến lược: Envelope/Jars, 50/30/20, Pay Yourself First. Phase này tạo phần "planned" của budget loop; chưa so sánh actual (Phase 5) nhưng đã có preview, copy tháng trước, chỉnh allocations và activate budget.

## 3. Scope

**In scope**
- Bảng `budgets`, `budget_allocations` cốt lõi.
- `budget_service` deterministic với strategy functions:
  - `create_envelope_budget()`
  - `create_fifty_thirty_twenty_reference()`
  - `create_pyf_budget()`
  - `copy_from_previous_month()`
- Envelope/Jars preset: Essential, Fun, Shopping, Saving, Unexpected; mapping jar → categories quyết định ở phase này và lưu trong `app_settings`.
- 50/30/20 tính từ `expected_income`: 50% essential, 30% wants, 20% savings; hiển thị là "tham khảo", không phải luật, và so sánh với budget custom của user.
- PYF: lấy `savings_target` trước, phần còn lại phân bổ theo nhóm.
- API CRUD draft/active budget; wizard UI `/budget/new` chọn strategy → preview → chỉnh → lưu.
- Unit tests với income `25,000,000` có số phân bổ chính xác.

**Out of scope**
- So sánh actual/variance/drill-down (Phase 5).
- Goals chi tiết và GoalContribution (Phase 11); Phase 4 chỉ có `savings_target` tổng.
- Flexible zones comfort/warning (Phase 9).
- AI budget advice (Phase 8) hoặc coach (Phase 10).

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`budgets`:
- `id UUID PK`, `user_id UUID NULL`
- `period_month DATE NOT NULL UNIQUE` — luôn ngày 1 của tháng
- `strategy TEXT NOT NULL CHECK IN ('envelope','fifty_thirty_twenty','pyf')`
- `expected_income BIGINT NOT NULL CHECK (expected_income >= 0)`
- `savings_target BIGINT NULL CHECK (savings_target >= 0)`
- `status TEXT NOT NULL DEFAULT 'draft' CHECK IN ('draft','active','closed')`
- timestamps

`budget_allocations`:
- `id UUID PK`, `budget_id UUID FK budgets(id) ON DELETE CASCADE`
- `group TEXT NOT NULL CHECK IN ('essential','wants','savings','irregular')`
- `category_id UUID FK categories(id) NULL`
- `jar_name TEXT NULL` — dùng cho envelope jar gom nhiều category hoặc savings
- `planned_amount BIGINT NOT NULL CHECK (planned_amount >= 0)`
- `created_at`, `updated_at`
- CHECK: có `category_id` **hoặc** `jar_name`.
- Index: `(budget_id)`, `(category_id)`.

`app_settings` seed/update key `budget_jar_category_map`:
```json
{
  "Essential": ["housing", "food", "transport", "utilities", "health", "education"],
  "Fun": ["entertainment", "gifts"],
  "Shopping": ["shopping", "electronics"],
  "Saving": [],
  "Unexpected": ["other"]
}
```

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/budgets` | Danh sách budget | `?from=2026-10-01&to=2026-12-01` | `{ "items": [BudgetRead] }` |
| GET | `/api/v1/budgets/{id}` | Chi tiết budget + allocations | — | `BudgetRead` |
| POST | `/api/v1/budgets/preview` | Tính preview strategy, chưa lưu | `{ "period_month": "2026-10-01", "strategy": "pyf", "expected_income": 25000000, "savings_target": 5000000 }` | `{ "budget": BudgetDraft, "reference_50_30_20": ... }` |
| POST | `/api/v1/budgets` | Lưu budget draft/active từ preview đã chỉnh | `BudgetCreate` | `201 BudgetRead` |
| PATCH | `/api/v1/budgets/{id}` | Sửa expected_income/status/allocations | `BudgetUpdate` | `BudgetRead` |
| POST | `/api/v1/budgets/copy-from-previous` | Copy budget tháng trước sang tháng mới | `{ "from_month": "2026-09-01", "to_month": "2026-10-01" }` | `201 BudgetRead` |
| DELETE | `/api/v1/budgets/{id}` | Xoá draft budget | — | `204` |

Quy tắc service:
- Chỉ một `active` budget mỗi `period_month`; tạo trùng trả 409.
- `period_month` normalize về ngày 1; nếu request không phải ngày 1 → 422.
- Tổng planned có thể nhỏ hơn expected_income; nếu lớn hơn thì trả warning ở preview và yêu cầu user xác nhận khi lưu.
- `copy_from_previous_month` copy allocations và strategy, không copy status `active` mặc định là `draft`.

### 4.3 AI (nếu có)

Không dùng AI trong Phase 4. Tất cả chiến lược budget là deterministic trong `services/budget_service.py`; không cần `OPENAI_API_KEY`; test không mock AI.

### 4.4 Frontend

- Route `/budget/new`: `BudgetWizard`.
- Step 1: chọn tháng, nhập `expected_income`, chọn strategy (`Envelope/Jars`, `50/30/20`, `Pay Yourself First`) hoặc "Copy tháng trước".
- Step 2: strategy-specific input:
  - Envelope: chỉnh amount cho Essential/Fun/Shopping/Saving/Unexpected.
  - 50/30/20: preview tự tính, cho phép "Dùng làm budget" hoặc chỉ xem reference.
  - PYF: nhập `savings_target`, preview phần còn lại.
- Step 3: `AllocationPreviewTable` cho chỉnh từng planned_amount, tổng planned vs expected_income, warning nếu lệch.
- Nút "Lưu draft" và "Kích hoạt".
- `/budget` nếu chưa có budget tháng hiện tại thì hiển thị CTA "Tạo budget tháng này".

## 5. Task breakdown

- [x] T1 Migration + ORM models `budgets`, `budget_allocations`; seed `budget_jar_category_map`
- [x] T2 Pydantic schemas `BudgetCreate/Update/Read`, `BudgetAllocationRead`, `BudgetPreviewRequest/Response`
- [x] T3 Implement `budget_service` validation chung: period_month, unique active, sum warnings
- [x] T4 Implement strategy `envelope` với preset jars + jar/category mapping
- [x] T5 Implement strategy `fifty_thirty_twenty` reference và comparison với custom budget
- [x] T6 Implement strategy `pyf`: savings_target trước, distribute remaining
- [x] T7 Implement `copy_from_previous_month`
- [x] T8 Routers `/api/v1/budgets*` + API tests 201/409/422
- [x] T9 Unit tests exact allocation amount với expected_income `25_000_000`
- [x] T10 UI `/budget/new` wizard + preview/edit/save
- [x] T11 CTA từ `/budget` hoặc `/` khi chưa có budget; gen OpenAPI types
- [x] T12 Cập nhật docs/PROGRESS/handoff + commit `phase-04: budget engine`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_budget_service.py tests/api/test_budgets.py
pytest

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest)**
| # | Input | Kỳ vọng |
|---|---|---|
| 1 | `period_month=2026-10-15` | 422, phải là ngày 1 |
| 2 | Tạo active budget `2026-10-01` hai lần | lần 2 trả 409 |
| 3 | Envelope income `25,000,000` preset | Essential `13,000,000`; Fun `3,000,000`; Shopping `2,000,000`; Saving `5,000,000`; Unexpected `2,000,000` |
| 4 | 50/30/20 income `25,000,000` | essential `12,500,000`; wants `7,500,000`; savings `5,000,000` |
| 5 | PYF income `25,000,000`, savings_target `5,000,000` | savings `5,000,000`; remaining `20,000,000`; essential `12,000,000`; wants `6,000,000`; irregular `2,000,000` |
| 6 | PYF savings_target `30,000,000`, income `25,000,000` | 422 hoặc preview warning hard error: target > income |
| 7 | Copy budget Sep → Oct | allocations amount bằng Sep, period_month Oct, status `draft` |
| 8 | BudgetAllocation không có `category_id` lẫn `jar_name` | 422 |
| 9 | Custom budget planned `27,000,000` với income `25,000,000` | preview có warning `planned_exceeds_income=2,000,000` |

**Kịch bản thao tác UI**
1. Mở `/budget/new`, chọn tháng 10/2026, income 25.000.000, strategy 50/30/20 → preview 12.500.000 / 7.500.000 / 5.000.000.
2. Chuyển sang PYF, nhập savings target 5.000.000 → preview savings trước, remaining 20.000.000.
3. Sửa Fun từ 3.000.000 xuống 2.500.000, lưu draft → mở lại budget thấy số đã sửa.
4. Bấm "Kích hoạt" → budget status active; tạo active cùng tháng bị báo đã tồn tại.
5. Tạo budget tháng 11 bằng "Copy tháng trước" → allocations giống tháng 10, status draft.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest`, `ruff check`, `npm run lint` xanh
- [x] Không có logic budget nào phụ thuộc AI hoặc OpenAI key
- [x] Data model thực tế khớp [data-model.md](../architecture/data-model.md) hoặc tài liệu đã cập nhật nếu lệch
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done
- [x] Mục 9 Handoff notes đã điền
- [x] Commit với message `phase-04: budget engine`

## 8. Rủi ro / câu hỏi mở

- Mapping jar → categories trong data-model để mở là `app_settings` hoặc bảng riêng; phase này chọn `app_settings` để đơn giản, nhưng nếu user muốn chỉnh mapping nhiều có thể cần bảng `jar_categories` sau.
- 50/30/20 là reference, không nên khiến user nghĩ app "bắt buộc" 50/30/20.
- `Saving` allocation không có category expense; Phase 11 sẽ nối sang Goals/PYF chi tiết.
- Unique `period_month` sẽ cần đổi thành `(user_id, period_month)` khi có auth.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-19
- **Đã làm:**
  - **DB** (migration `20261019_2af9a678b445_budget_engine`): `budgets` (UNIQUE `period_month`, CHECK ngày 1, `strategy`, `status`, tiền ≥ 0) và `budget_allocations` (CHECK `group`, `planned_amount >= 0`, `(category_id IS NOT NULL) <> (jar_name IS NOT NULL)`, FK `budget_id` CASCADE / `category_id` RESTRICT, index `budget_id`, `category_id`, thêm cột `position` để giữ thứ tự dòng). Seed `app_settings.budget_jar_category_map` (đúng mapping mục 4.1). Đã thử `upgrade → downgrade -1 → upgrade`. Chi tiết: [data-model.md § Phase 4](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế).
  - **`services/money.py`**: `allocate_by_weights(total, weights, step)` — chia theo tỉ lệ, mỗi phần là bội số `step` (1.000 đ), phần dư lớn nhất nhận phần lẻ, tổng luôn đúng bằng `total`; `format_vnd` cho thông báo lỗi.
  - **`services/budget_service.py`** (deterministic, không import `ai`): `create_envelope_budget` (5 hũ 52/12/8/20/8 %), `create_fifty_thirty_twenty_reference`, `create_pyf_budget` (savings trước, phần còn lại 60/30/10 essential/wants/irregular), `generate_allocations`, `compute_totals`, `compare_with_reference` (irregular gộp vào wants khi so 50/30/20), `over_income_amount`, **`allocation_scope`** (quy tắc khớp giao dịch cho Phase 5), `load_jar_map` / `load_jar_categories` / `list_jars`, `preview_budget`, `create_budget`, `update_budget`, `delete_budget`, `copy_from_previous_month`, `to_read`.
  - **API** `/api/v1/budgets`: `GET` (`from`/`to`), `GET /jars`, `POST /preview`, `POST` (201/409/422), `POST /copy-from-previous` (201/404/409), `GET/PATCH/DELETE /{id}`. `core/errors.ConflictError` (409).
  - **Frontend:** `/budget/new` = `BudgetWizard` (1. tháng + thu nhập + chọn strategy/PYF savings + "Copy tháng trước" → 2. `AllocationPreviewTable` sửa từng dòng, tổng/cảnh báo do backend tính lại (debounce, `useBudgetPreview`) → bảng "So với mốc 50/30/20" → 3. "Lưu nháp" / "Lưu & kích hoạt", checkbox xác nhận khi vượt thu nhập). `/budget` = `BudgetView` (chọn tháng `?month=`) → `BudgetEditor` (sửa thu nhập/số tiền, Kích hoạt / Chuyển về nháp / Đóng tháng / Mở lại, Xoá nháp) hoặc `BudgetEmptyState` (CTA "Tạo budget tháng này" + "Copy tháng trước"); trang chủ có `HomeBudgetCta` khi tháng hiện tại chưa có budget. Nav "Ngân sách" đã bật. `gen:api` đã chạy lại.
  - **Test:** 333 pass (không cần key) — `tests/unit/test_budget_service.py` (39: `allocate_by_weights` tổng đúng, 3 chiến lược với 25.000.000, tham khảo 50/30/20, `allocation_scope`), `tests/api/test_budgets.py` (35: đủ 9 test case mục 6 + CRUD, chuyển trạng thái, validate hũ/nhóm/trùng/chồng lấn, danh mục thu nhập/đã ẩn, cảnh báo, copy bỏ danh mục đã ẩn).
  - **Verify:** `ruff check`, `ruff format --check`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 5 kịch bản UI mục 6 đã chạy trên trình duyệt (kèm: PYF savings 30tr báo lỗi, sửa vượt thu nhập → cảnh báo + khoá nút lưu, sửa/lưu/xoá nháp trên `/budget`). Dữ liệu thử đã xoá khỏi DB dev.
- **Lệch so với plan (và lý do):**
  - **Dòng theo nhóm** (50/30/20, PYF) lưu `jar_name = group` (`essential`/`wants`/`savings`/`irregular`); actual ở Phase 5 khớp theo **`spending_type`** của giao dịch (essential → essential, non_essential → wants, irregular → irregular, savings không khớp chi tiêu). Hũ envelope khớp theo danh mục trong `budget_jar_category_map`; dòng có `category_id` khớp danh mục đó. Quy tắc nằm ở `budget_service.allocation_scope` (user chọn phương án này).
  - Service **chặn phân bổ chồng lấn** (cùng danh mục ở 2 dòng, hoặc vừa dòng nhóm vừa dòng danh mục) → 422 `overlapping_allocations` để actual không bị đếm 2 lần; dòng trùng → `duplicate_allocation`; hũ không có trong cấu hình → `unknown_jar`; dòng nhóm sai `jar_name` → `invalid_group_row`.
  - **Mỗi tháng chỉ 1 budget** (bất kể status — đúng UNIQUE `period_month` của data-model), không chỉ 1 active: tạo trùng tháng → 409 `budget_exists`; tháng đã có thì mở ra sửa.
  - Tổng planned > thu nhập: preview trả warning `planned_exceeds_income`; `POST`/`PATCH` trả 422 cùng code trừ khi gửi `confirm_over_income: true`.
  - PYF savings_target > income → **422** `savings_target_exceeds_income` (plan cho phép 422 hoặc warning).
  - `budgets.savings_target` = tổng planned nhóm `savings`, service tự đồng bộ khi lưu (`BudgetCreate` không nhận `savings_target` — tránh lệch với allocations).
  - Preset envelope 52/12/8/20/8 % (suy ra từ test case 13/3/2/5/2 triệu); PYF chia phần còn lại 60/30/10 (từ test case 12/6/2 triệu). Làm tròn tới 1.000 đ.
  - Preview nhận thêm `allocations` (tuỳ chọn) để UI gửi phân bổ đã chỉnh và nhận lại tổng/cảnh báo/so sánh — frontend không tự cộng tiền. Thêm `GET /budgets/jars` (hũ + danh mục) và cảnh báo `categories_not_in_jar` (danh mục chi chưa thuộc hũ nào), `budget_exists`.
  - Chuyển trạng thái: draft → active; active → draft/closed; closed → active. Budget `closed` không sửa được nội dung (409 `budget_closed`). Chỉ xoá được `draft` (409 `budget_not_draft`). Tạo mới với `closed` → 422.
  - `copy-from-previous`: `from_month` tuỳ chọn (mặc định tháng trước `to_month`); bỏ dòng có danh mục đã ẩn.
  - Thêm cột `budget_allocations.position` (thứ tự hiển thị, PYF savings đứng đầu). Cột `user_id` chỉ ở `budgets`.
  - Wizard gộp bước 1–2 của plan: nhập thu nhập/strategy (+ savings PYF) là thấy preview ngay; "chỉnh amount từng hũ" làm trực tiếp ở bảng bước 2. Tên hũ lưu tiếng Anh (`Essential`, `Fun`…) như plan, UI hiển thị tiếng Việt (Thiết yếu, Vui chơi, Mua sắm, Tiết kiệm, Dự phòng).
- **Nợ kỹ thuật / TODO để lại:**
  - Chưa có UI chỉnh `budget_jar_category_map` (đổi bằng SQL); chưa cho thêm/xoá dòng phân bổ hay phân bổ theo danh mục trên UI (API đã hỗ trợ dòng `category_id`).
  - Đổi strategy của budget đã lưu: chưa hỗ trợ (xoá nháp rồi tạo lại).
  - Unique `period_month` cần thành `(user_id, period_month)` khi có auth.
  - `budget_exists` cảnh báo ở preview so khớp theo tháng, không biết user đang sửa budget nào → `BudgetEditor` lọc bỏ.
  - Chưa có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_budget_service.py tests/api/test_budgets.py -q)`
  - `curl -s -X POST localhost:8000/api/v1/budgets/preview -H 'Content-Type: application/json' -d '{"period_month":"2026-10-01","strategy":"pyf","expected_income":25000000,"savings_target":5000000}'`
  - `curl -s localhost:8000/api/v1/budgets/jars`
  - `docker exec -it pfa-db psql -U pfa -d pfa -c "select value from app_settings where key='budget_jar_category_map';"`
- **Gợi ý cho phase tiếp theo (Phase 5 — Budget vs Actual):**
  - Dùng `budget_service.allocation_scope(budget.strategy, allocation, jar_ids)` để biết giao dịch chi nào thuộc dòng nào (`kind` = `category` | `jar` | `group`; `category_ids` hoặc `spending_types`; nhóm `savings` rỗng → actual 0). `load_jar_categories(db)` trả hũ → danh mục (kể cả danh mục đã ẩn).
  - Service đã đảm bảo các dòng của 1 budget không chồng lấn → cộng actual từng dòng không bị đếm trùng.
  - `/budget` hiện là `BudgetEditor` (planned); Phase 5 thêm cột actual/variance vào bảng hoặc tách tab "Theo dõi" / "Kế hoạch". `HomeBudgetCta` ở trang chủ có thể thay bằng `MonthSummaryCards` khi đã có budget.
