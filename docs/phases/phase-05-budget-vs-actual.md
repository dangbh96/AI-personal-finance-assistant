# Phase 05 — Budget vs Actual

| | |
|---|---|
| **ID** | `phase-05-budget-vs-actual` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 4 |
| **Mở khoá** | Phase 6, 9 |
| **Milestone** | **M3 — Budget loop hoàn chỉnh** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 4](./phase-04-budget-engine.md)
2. [glossary.md](../product/glossary.md) — `actual`, `variance`, group, budget allocation
3. [vision.md](../product/vision.md) — actual > budget không mặc định là sửa budget; evidence trước lời khuyên
4. [data-model.md](../architecture/data-model.md) — `budgets`, `budget_allocations`, `transactions`
5. [core-loop.md](../architecture/core-loop.md) — budget loop và review
6. [budget-adjustment.md](../architecture/budget-adjustment.md) — top contributor/one-off là nền cho Phase 8
7. [backend-components.md](../architecture/backend-components.md) — aggregate/variance nằm trong deterministic services
8. [frontend-structure.md](../architecture/frontend-structure.md) — `/budget`, home month summary cards
9. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu: Phase 4 Done; có active budget tháng với allocations; transactions Phase 1 có dữ liệu seed/demo; chưa có aggregate actual theo budget.

## 2. Mục tiêu & giá trị cho user

User thấy ngân sách tháng đang chạy so với chi tiêu thực tế: planned, actual, variance, phần trăm đã dùng, khoản nào gây vượt. Đây là mảnh cuối để budget loop dùng được trước khi thêm review AI.

## 3. Scope

**In scope**
- Aggregate actual theo từng `budget_allocations` trong tháng budget.
- Tính `variance = actual - planned`, `remaining = planned - actual`, `used_percent`.
- Top contributor detection: nếu một giao dịch chiếm ≥60% phần overspend của allocation thì trả về giao dịch đó; ví dụ overspend `1,200,000`, một giao dịch `900,000` → share 75%.
- Income actual vs `expected_income`, net actual trong tháng.
- Pro-rata month progress: ngày đã qua / số ngày trong tháng; cảnh báo sớm nếu used_percent vượt progress đáng kể.
- API status budget month và drill-down transactions.
- Home page month summary cards; `/budget` table + drill-down.
- Seed scenario test với số liệu cố định.

**Out of scope**
- Flexible comfort/warning zones (Phase 9); Phase 5 chỉ có status đơn giản planned/over/pro-rata.
- AI explanation/advice (Phase 8); chỉ trả evidence deterministic.
- Weekly/monthly review narrative (Phase 6, 7).
- Chỉnh budget allocation nâng cao; chỉ link về Phase 4 edit nếu đã có.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Không cần bảng mới. Sử dụng:
- `budgets.period_month`, `expected_income`, `status`.
- `budget_allocations.group`, `category_id`, `jar_name`, `planned_amount`.
- `transactions.direction`, `amount`, `occurred_on`, `category_id`, `spending_type`, `note`, `source`.
- `app_settings.budget_jar_category_map` nếu allocation là jar.

Nếu cần performance về sau có thể thêm materialized view, nhưng Phase 5 dùng SQL aggregate trực tiếp và index Phase 1: `transactions(occurred_on)`, `transactions(category_id, occurred_on)`.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/budgets/{id}/status` | Planned vs actual cho budget | `?today=2026-10-20` (optional, testable) | `BudgetStatusRead` |
| GET | `/api/v1/budgets/current/status` | Status active budget của tháng hiện tại | `?month=2026-10-01&today=2026-10-20` | `BudgetStatusRead` hoặc 404 |
| GET | `/api/v1/budget-allocations/{id}/transactions` | Drill-down giao dịch thuộc allocation | `?page=1&page_size=50` | `{ "items": [TransactionRead], "total": 12 }` |
| GET | `/api/v1/dashboard/month-summary` | Cards trang chủ | `?month=2026-10-01&today=2026-10-20` | income/expense/net/budget_progress/top_over |

Service:
- `analytics_service.get_budget_status(budget_id, today)` tính start/end tháng, day progress.
- Allocation matching (quy tắc chốt ở Phase 4 — dùng `budget_service.allocation_scope`, xem [data-model.md § Phase 4](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế)):
  - Nếu `category_id` khác null: actual = expense transactions cùng category trong tháng.
  - Nếu `jar_name` khác null và budget `envelope`: map jar → category slugs từ `app_settings`; actual = expense transactions thuộc các categories đó.
  - Nếu `jar_name` khác null và budget `fifty_thirty_twenty` / `pyf` (dòng nhóm, `jar_name = group`): actual = expense transactions có `spending_type` tương ứng (`essential` → essential, `non_essential` → wants, `irregular` → irregular).
  - `group='savings'` không có actual expense ở Phase 5; actual = 0 cho tới Phase 11 hoặc nếu có category saving riêng sau này.
- Income actual = tổng transactions `direction='income'` trong tháng.
- Top contributor: chỉ xét allocation có `actual > planned`; `overspend = actual - planned`; tìm transaction lớn nhất trong scope; nếu `largest.amount / overspend >= 0.6` thì trả `top_contributor`.
- Pro-rata: `month_progress = elapsed_days / days_in_month`; `expected_spend_to_date = planned * month_progress`; `pace_status = ahead|on_track|under` với tolerance 10 percentage points.

### 4.3 AI (nếu có)

Không dùng AI trong Phase 5. Các số liệu actual, variance, top contributor, pro-rata đều deterministic trong service và phải có unit test. Narrative AI để Phase 6/8 dùng lại evidence này.

### 4.4 Frontend

- `/`: thêm `MonthSummaryCards`
  - Thu nhập thực tế vs expected income.
  - Tổng chi vs tổng planned expense.
  - Net tháng.
  - Top over-budget allocation nếu có.
- `/budget`: `BudgetVsActualTable`
  - Cột: Allocation/Jar, Planned, Actual, Remaining/Over, Used %, Pace, Top contributor.
  - Badge màu đơn giản: green `on_track`, yellow `ahead_of_pace`, red `over_budget`.
  - Expand row hoặc side panel `AllocationDrillDown` hiển thị giao dịch trong allocation.
- Empty state: chưa có active budget → CTA "Tạo budget"; chưa có giao dịch → hiển thị actual 0.
- Frontend chỉ format số; không tự tính variance.

## 5. Task breakdown

- [x] T1 Thiết kế schemas `BudgetStatusRead`, `AllocationStatusRead`, `TopContributorRead`, `MonthSummaryRead`
- [x] T2 Implement SQL aggregate actual theo category allocation
- [x] T3 Implement jar allocation matching từ `budget_jar_category_map`
- [x] T4 Implement income vs expected, totals, variance, used_percent
- [x] T5 Implement top contributor detection với threshold 60% overspend
- [x] T6 Implement pro-rata month progress + pace_status testable bằng `today`
- [x] T7 API routes `/budgets/{id}/status`, `/budgets/current/status`, `/budget-allocations/{id}/transactions`, `/dashboard/month-summary`
- [x] T8 Seed scenario fixture/script cho budget tháng 10/2026 + transactions cố định
- [x] T9 Unit/API tests exact numbers, including overspend 1,200,000 và contributor 900,000
- [x] T10 UI home month summary cards
- [x] T11 UI `/budget` table + drill-down transactions; gen OpenAPI types
- [x] T12 Cập nhật docs/PROGRESS/handoff + commit `phase-05: budget vs actual`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_budget_status.py tests/api/test_budget_status.py
python -m app.scripts.seed_demo --months 3
python -m app.scripts.seed_scenario --reset
pytest

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest)**
| # | Dữ liệu | Kỳ vọng |
|---|---|---|
| 1 | Budget food planned `4,000,000`; transactions food `55,000`, `60,000`, `4,385,000` | actual `4,500,000`, variance `500,000`, used_percent `112.5` |
| 2 | Shopping planned `2,000,000`; actual `3,200,000`; largest transaction tai nghe `900,000` | overspend `1,200,000`; top_contributor amount `900,000`, share `0.75` |
| 3 | Transport planned `1,000,000`; actual `700,000` | variance `-300,000`, remaining `300,000`, status `on_track` |
| 4 | Income expected `25,000,000`; income transactions salary `25,000,000`, freelance `4,000,000` | income_actual `29,000,000`, income_variance `4,000,000` |
| 5 | today `2026-10-15`, month 31 ngày, planned food `4,000,000`, actual `3,000,000` | progress ~`0.48`; expected_to_date ~`1,935,484`; pace_status `ahead` |
| 6 | Allocation jar Essential maps housing+food+transport; actual từng category 5,000,000 + 4,500,000 + 700,000 | jar actual `10,200,000` |
| 7 | Savings allocation planned `5,000,000`, chưa có Phase 11 | actual `0`, không tính là expense overspend |
| 8 | No active budget current month | `/budgets/current/status` trả 404; `/dashboard/month-summary` vẫn trả income/expense nếu có transactions |
| 9 | Drill-down allocation food | chỉ trả transactions category food trong budget month, sort date desc |

**Seed scenario test**
| Thành phần | Planned | Actual | Kỳ vọng UI/API |
|---|---:|---:|---|
| Nhà ở | 5,000,000 | 5,000,000 | on track |
| Ăn uống | 4,000,000 | 4,500,000 | over 500,000 |
| Đi lại | 1,000,000 | 700,000 | under 300,000 |
| Mua sắm | 2,000,000 | 3,200,000 | over 1,200,000; top contributor 900,000 |
| Giải trí | 1,000,000 | 600,000 | under 400,000 |
| Income | expected 25,000,000 | 25,000,000 | variance 0 |

**Kịch bản thao tác UI**
1. Seed scenario, mở `/` → cards hiển thị Thu nhập 25.000.000, Chi tiêu theo budget month, Net đúng.
2. Mở `/budget` → bảng có 5 dòng allocation/category với planned/actual/variance đúng như seed.
3. Dòng Mua sắm có badge đỏ và text "900.000 ₫ từ 1 giao dịch" vì 900k chiếm 75% overspend.
4. Click dòng Mua sắm → drill-down chỉ thấy các giao dịch mua sắm tháng 10/2026.
5. Đổi `today` trong test/dev mock sang ngày 15 → pace của Ăn uống báo ahead nếu actual vượt pro-rata.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest`, `ruff check`, `npm run lint` xanh
- [x] API status không dùng AI và mọi số tiền là integer VND
- [x] Home summary cards và `/budget` dùng dữ liệu backend, không tự tính ở frontend
- [x] Seed scenario test chứng minh top contributor đúng
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật đánh dấu **M3 — Budget loop hoàn chỉnh**
- [x] Mục 9 Handoff notes đã điền
- [x] Commit với message `phase-05: budget vs actual`

## 8. Rủi ro / câu hỏi mở

- Allocation dạng jar có thể overlap categories nếu mapping bị cấu hình sai; service cần detect duplicate category trong nhiều jar và warning hoặc reject.
- Savings actual tạm thời là 0 tới Phase 11; UI phải ghi chú "Savings sẽ nối với Goals/PYF ở Phase 11" để tránh hiểu nhầm.
- Pro-rata cảnh báo sớm không thay thế Flexible Zones Phase 9; tránh thiết kế UI quá phức tạp ở Phase 5.
- Data-model không có bảng materialized aggregate; nếu dữ liệu lớn sau này có thể cần cache nhưng hiện chưa cần.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-20
- **Đã làm:**
  - **Không có migration.** `transaction_repository`: `totals_by_direction`, `expense_totals_by_category_and_spending_type` (1 aggregate gộp `(category_id, spending_type)` cho cả tháng), `largest_in_scope`, `list_in_scope` (giao dịch chi trong kỳ thuộc danh mục **hoặc** spending_type cho trước). `budget_repository.get_allocation`.
  - **`services/analytics_service.py`** (deterministic, không import `ai`): hàm thuần `month_progress` (ngày đã qua **tính cả hôm nay**; tháng chưa tới = 0, đã qua = đủ ngày), `used_percent` (1 chữ số), `expected_to_date` (`round_vnd(planned × progress)`), `pace_status` (dung sai 10 điểm %, đúng biên vẫn `on_track`), `tracking_status`, `top_contributor_share` (≥ 60%, tối đa 1), `scope_actual`, `evaluate_allocation`, `effective_scope` (= `budget_service.allocation_scope`, riêng nhóm `savings` rỗng); hàm DB `get_budget_status`, `get_budget_status_by_id`, `get_current_status`, `get_month_summary`, `list_allocation_transactions`. Tỉ lệ tính bằng `Fraction`, làm tròn half-up khi trả về.
  - **Schemas** `schemas/analytics.py`: `BudgetStatusRead` (`progress`, `totals`, `allocations`), `AllocationStatusRead` (planned/actual/variance/remaining/used_percent/transaction_count/expected_to_date/pace_status/status/top_contributor + `scope` gồm danh mục / spending_type), `BudgetStatusTotals`, `TopContributorRead`, `MonthProgressRead`, `MonthSummaryRead`.
  - **API:** `GET /budgets/{id}/status?today=`, `GET /budgets/current/status?month=&today=`, `GET /budget-allocations/{id}/transactions?page=&page_size=` (trả `TransactionList`), `GET /dashboard/month-summary?month=&today=`. `today` mặc định ngày của server; `month` nhận ngày bất kỳ trong tháng.
  - **Seed scenario** `app/scripts/seed_scenario.py` (`python -m app.scripts.seed_scenario [--reset]`): budget active 10/2026 (`fifty_thirty_twenty`, 5 dòng theo danh mục đúng bảng mục 6) + 59 giao dịch cố định 01–20/10; dữ liệu khai báo trong module, test dùng lại `seed(db, reset=True)`. Ăn uống được dựng từ nhiều khoản ≤ 250.000 để vượt 500.000 mà **không** có top contributor.
  - **Frontend:** `/budget` có tabs **Theo dõi** (`BudgetTracking` → `MonthSummaryCards` + `MonthProgressCard` + `BudgetVsActualTable` với badge trạng thái, thanh % đã dùng + vạch % tháng, cột Nhịp, "900.000 ₫ từ 1 giao dịch"; bấm dòng mở `AllocationDrillDown` có phân trang, tô giao dịch top contributor) và **Kế hoạch** (`BudgetEditor` Phase 4); `?tab=track|plan`, `?today=YYYY-MM-DD` để thử pro-rata. Trang chủ: `HomeDashboard` (= `QuickAddBox` + `HomeMonthSummary`, lưu xong tự tải lại tóm tắt) thay `HomeBudgetCta` (đã xoá). `lib/format`: `formatSignedVND`, `formatPercent`. `gen:api` đã chạy lại.
  - **Test:** 369 pass (+36): `tests/unit/test_budget_status.py` (17, hàm thuần) và `tests/api/test_budget_status.py` (19: đủ 9 test case mục 6 + dưới ngưỡng 60%, dòng nhóm PYF theo spending_type, chi ngoài ngân sách, giao dịch ngoài tháng, `current/status` theo `month` + budget closed, 404, phân trang drill-down, seed scenario cuối tháng / giữa tháng / cần `--reset`).
  - **Verify:** `alembic upgrade head`, `ruff check`, `ruff format --check`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 5 kịch bản UI mục 6 đã chạy trên trình duyệt (trang chủ, bảng 5 dòng, Mua sắm "900.000 ₫ từ 1 giao dịch", drill-down chỉ giao dịch mua sắm 10/2026, `?today=2026-10-15` → Ăn uống "Nhanh hơn nhịp") + tab Kế hoạch, tháng trống.
  - **DB dev hiện có:** kịch bản tháng 10/2026 (`seed_scenario`) + dữ liệu demo 06–09/2026 (`seed_demo --months 3 --end 2026-09-30`, 211 giao dịch, chưa có budget) — đủ lịch sử cho Phase 6–8.
- **Lệch so với plan (và lý do):**
  - Thêm trạng thái dòng **`not_tracked`** cho nhóm `savings` (actual 0, không pace, không tính vượt) bên cạnh `on_track` / `ahead_of_pace` / `over_budget`; dòng savings có `category_id` cũng actual = 0 (chi tiêu danh mục đó rơi vào `unbudgeted_actual`).
  - `status` dòng: `over_budget` nếu actual > planned (planned = 0 mà có chi cũng là vượt), ngược lại `ahead_of_pace` nếu pace = `ahead`, còn lại `on_track`. `pace_status = null` khi planned = 0.
  - `top_contributor.share` = `min(1, amount / overspend)` — giao dịch lớn hơn cả phần vượt được tính là gây ra toàn bộ phần vượt (plan không nói trường hợp share > 1).
  - Totals thêm `expense_actual` (= **mọi** giao dịch chi trong tháng), `allocated_actual`, `unbudgeted_actual` (chi không thuộc dòng nào, vd danh mục chưa vào hũ), `expense_used_percent`, `savings_planned`, `over_budget_count`; `expense_variance = expense_actual − expense_planned`.
  - `/budgets/current/status` và phần `budget` của month-summary nhận budget **active hoặc closed** (tháng đã đóng vẫn xem được); nháp → 404 `budget_not_active`, chưa có → 404 `budget_not_found`. Month-summary trả thêm `budget_status` để trang chủ biết "chưa có" (CTA) hay "nháp" (nhắc kích hoạt). `/budgets/{id}/status` dùng được cho mọi trạng thái (tab Theo dõi hiện cả với nháp).
  - Drill-down trả `TransactionList` (`items/total/page/page_size`) như `/transactions`.
  - Script seed scenario riêng (`seed_scenario.py`) thay vì gộp vào `seed_demo`; lệnh Verify thêm `python -m app.scripts.seed_scenario --reset`. Strategy của kịch bản là `fifty_thirty_twenty` với dòng theo danh mục (plan không chỉ định).
  - UI dùng tabs Theo dõi / Kế hoạch (gợi ý trong handoff Phase 4) thay vì gộp cột actual vào bảng planned.
- **Nợ kỹ thuật / TODO để lại:**
  - Pro-rata tuyến tính nên khoản cố định trả đầu tháng (tiền nhà) bị báo "Chi nhanh hơn nhịp" giữa tháng (seed scenario ngày 20: Nhà ở vàng) — Phase 9 (zones) / Phase 12 (lịch khoản định kỳ) nên xử lý.
  - Ngưỡng 60% có thể gắn top contributor cho khoản thường xuyên khi phần vượt nhỏ (vd vượt 100.000 với 1 lần đi chợ 300.000). Phase 8 nên kết hợp `spending_type = irregular` / lịch sử trước khi kết luận "one-off".
  - `today` mặc định theo giờ server; frontend luôn gửi `today` của trình duyệt.
  - Chưa có test tự động frontend (Phase 18). Unique `period_month` vẫn cần `(user_id, period_month)` khi có auth.
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_budget_status.py tests/api/test_budget_status.py -q)`
  - `(cd backend && python -m app.scripts.seed_scenario --reset)`
  - `curl -s "localhost:8000/api/v1/budgets/current/status?month=2026-10-01&today=2026-10-15"`
  - `curl -s "localhost:8000/api/v1/dashboard/month-summary?today=2026-10-20"`
- **Gợi ý cho phase tiếp theo (Phase 6 — Weekly review):**
  - Evidence cho AI lấy từ `analytics_service.get_budget_status(db, budget, today)`: mỗi dòng có `variance`, `used_percent`, `pace_status`, `expected_to_date`, `top_contributor` (giao dịch + `share`); tổng ở `totals`. Narrative chỉ được dùng số có trong các metrics này (ADR-005).
  - Tổng hợp theo tuần chưa có: thêm hàm kiểu `transaction_repository.expense_totals_by_category_and_spending_type(db, week_start, week_end)` (đã nhận khoảng ngày bất kỳ) + `money.week_range`.
  - DB dev có 4 tháng demo (06–09) + kịch bản 10/2026 để thử review tuần.
