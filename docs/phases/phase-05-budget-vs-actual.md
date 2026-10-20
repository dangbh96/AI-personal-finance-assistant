# Phase 05 — Budget vs Actual

| | |
|---|---|
| **ID** | `phase-05-budget-vs-actual` |
| **Trạng thái** | Not started |
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

- [ ] T1 Thiết kế schemas `BudgetStatusRead`, `AllocationStatusRead`, `TopContributorRead`, `MonthSummaryRead`
- [ ] T2 Implement SQL aggregate actual theo category allocation
- [ ] T3 Implement jar allocation matching từ `budget_jar_category_map`
- [ ] T4 Implement income vs expected, totals, variance, used_percent
- [ ] T5 Implement top contributor detection với threshold 60% overspend
- [ ] T6 Implement pro-rata month progress + pace_status testable bằng `today`
- [ ] T7 API routes `/budgets/{id}/status`, `/budgets/current/status`, `/budget-allocations/{id}/transactions`, `/dashboard/month-summary`
- [ ] T8 Seed scenario fixture/script cho budget tháng 10/2026 + transactions cố định
- [ ] T9 Unit/API tests exact numbers, including overspend 1,200,000 và contributor 900,000
- [ ] T10 UI home month summary cards
- [ ] T11 UI `/budget` table + drill-down transactions; gen OpenAPI types
- [ ] T12 Cập nhật docs/PROGRESS/handoff + commit `phase-05: budget vs actual`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_budget_status.py tests/api/test_budget_status.py
python -m app.scripts.seed_demo --months 3
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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest`, `ruff check`, `npm run lint` xanh
- [ ] API status không dùng AI và mọi số tiền là integer VND
- [ ] Home summary cards và `/budget` dùng dữ liệu backend, không tự tính ở frontend
- [ ] Seed scenario test chứng minh top contributor đúng
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật đánh dấu **M3 — Budget loop hoàn chỉnh**
- [ ] Mục 9 Handoff notes đã điền
- [ ] Commit với message `phase-05: budget vs actual`

## 8. Rủi ro / câu hỏi mở

- Allocation dạng jar có thể overlap categories nếu mapping bị cấu hình sai; service cần detect duplicate category trong nhiều jar và warning hoặc reject.
- Savings actual tạm thời là 0 tới Phase 11; UI phải ghi chú "Savings sẽ nối với Goals/PYF ở Phase 11" để tránh hiểu nhầm.
- Pro-rata cảnh báo sớm không thay thế Flexible Zones Phase 9; tránh thiết kế UI quá phức tạp ở Phase 5.
- Data-model không có bảng materialized aggregate; nếu dữ liệu lớn sau này có thể cần cache nhưng hiện chưa cần.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
