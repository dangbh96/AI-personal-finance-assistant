# Phase 04 — Budget Engine

| | |
|---|---|
| **ID** | `phase-04-budget-engine` |
| **Trạng thái** | Not started |
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

- [ ] T1 Migration + ORM models `budgets`, `budget_allocations`; seed `budget_jar_category_map`
- [ ] T2 Pydantic schemas `BudgetCreate/Update/Read`, `BudgetAllocationRead`, `BudgetPreviewRequest/Response`
- [ ] T3 Implement `budget_service` validation chung: period_month, unique active, sum warnings
- [ ] T4 Implement strategy `envelope` với preset jars + jar/category mapping
- [ ] T5 Implement strategy `fifty_thirty_twenty` reference và comparison với custom budget
- [ ] T6 Implement strategy `pyf`: savings_target trước, distribute remaining
- [ ] T7 Implement `copy_from_previous_month`
- [ ] T8 Routers `/api/v1/budgets*` + API tests 201/409/422
- [ ] T9 Unit tests exact allocation amount với expected_income `25_000_000`
- [ ] T10 UI `/budget/new` wizard + preview/edit/save
- [ ] T11 CTA từ `/budget` hoặc `/` khi chưa có budget; gen OpenAPI types
- [ ] T12 Cập nhật docs/PROGRESS/handoff + commit `phase-04: budget engine`

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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest`, `ruff check`, `npm run lint` xanh
- [ ] Không có logic budget nào phụ thuộc AI hoặc OpenAI key
- [ ] Data model thực tế khớp [data-model.md](../architecture/data-model.md) hoặc tài liệu đã cập nhật nếu lệch
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done
- [ ] Mục 9 Handoff notes đã điền
- [ ] Commit với message `phase-04: budget engine`

## 8. Rủi ro / câu hỏi mở

- Mapping jar → categories trong data-model để mở là `app_settings` hoặc bảng riêng; phase này chọn `app_settings` để đơn giản, nhưng nếu user muốn chỉnh mapping nhiều có thể cần bảng `jar_categories` sau.
- 50/30/20 là reference, không nên khiến user nghĩ app "bắt buộc" 50/30/20.
- `Saving` allocation không có category expense; Phase 11 sẽ nối sang Goals/PYF chi tiết.
- Unique `period_month` sẽ cần đổi thành `(user_id, period_month)` khi có auth.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
