# Phase 12 — Calendar / Forecast

| | |
|---|---|
| **ID** | `phase-12-calendar-forecast` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 11 |
| **Mở khoá** | Phase 18 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 11
2. [glossary.md](../product/glossary.md) — `RecurringTransaction`, `forecast`, `source = "recurring"`
3. [vision.md](../product/vision.md) — Financial Calendar trong feature map
4. [brainstorm-original.md](../product/brainstorm-original.md#14-ai-financial-calendar) — icon salary/rent/credit card/internet/goal saving
5. [core-loop.md](../architecture/core-loop.md) — theo dõi thực tế + dự báo dòng tiền
6. [data-model.md](../architecture/data-model.md) — `recurring_transactions`, `transactions.recurring_id`, `app_settings`
7. [backend-components.md](../architecture/backend-components.md) — `forecast_service`
8. [frontend-structure.md](../architecture/frontend-structure.md) — route `/calendar`
9. [phase-roadmap.md](../architecture/phase-roadmap.md) — Phase 12 mở khoá hardening
10. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: Phase 11 đã Done; có goals, goal_contributions, budget/PYF, transactions đủ lịch sử tối thiểu để phát hiện recurring; `app_settings` đã tồn tại từ Phase 1.

## 2. Mục tiêu & giá trị cho user

User nhìn được lịch các khoản tiền sắp đến (lương, thuê nhà, thẻ tín dụng, internet, goal saving) và đường dự báo số dư 30/60 ngày tới để biết ngày nào có nguy cơ thiếu tiền. Phase này giúp user chủ động trước các khoản định kỳ thay vì chỉ review sau khi đã chi.

## 3. Scope

**In scope**
- Bảng `recurring_transactions` + cột `transactions.recurring_id`.
- Manual CRUD recurring transaction: name, direction, amount, category, spending_type, frequency, next due date, active.
- Recurring detection deterministic từ lịch sử: cùng category + amount tương tự ±10% + interval gần monthly/weekly trong ≥3 occurrences; tạo suggestion để user xác nhận.
- `next_due_on` calculation, xử lý ngày 31 trong tháng ngắn bằng last day of month.
- `forecast_service`: daily projected balance cho N=30/60 ngày.
- Quyết định current balance: user nhập `starting_balance` trong `app_settings`; forecast không cố đoán số dư ngân hàng.
- Low-balance warning day khi projected balance < `low_balance_threshold`.
- Tạo giao dịch thật từ due recurring item (`source='recurring'`, `recurring_id` set).
- UI `/calendar`: month view icon + list upcoming + forecast line chart.

**Out of scope**
- Kết nối ngân hàng/credit card thật.
- Auto-create transaction nền không cần user xác nhận.
- Notification/email/push.
- AI agent tự quyết định recurring; Phase này deterministic và user xác nhận.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`recurring_transactions`: `id UUID PK`, `user_id UUID NULL`, `name TEXT`, `direction TEXT CHECK direction IN ('income','expense')`, `amount BIGINT CHECK amount > 0`, `category_id UUID FK categories(id)`, `spending_type TEXT NULL`, `frequency TEXT CHECK frequency IN ('weekly','monthly','yearly')`, `day_of_month INT NULL`, `day_of_week INT NULL`, `next_due_on DATE`, `auto_detected BOOL DEFAULT false`, `active BOOL DEFAULT true`, timestamps.
- Validate: income có `spending_type IS NULL`; expense có `spending_type IS NOT NULL`.
- Monthly cần `day_of_month BETWEEN 1 AND 31`; weekly cần `day_of_week BETWEEN 1 AND 7` (ISO Monday=1).
- Index `(active, next_due_on)`, `(category_id)`.

`transactions`: thêm `recurring_id UUID NULL FK recurring_transactions(id)`; `source` nhận giá trị `recurring`.

`app_settings` thêm keys:
- `forecast.starting_balance`: số nguyên VND do user nhập, ví dụ `12000000`.
- `forecast.low_balance_threshold`: mặc định `1000000`.
- `forecast.goal_saving_day_of_month`: mặc định `10` để đặt icon 🎯 nếu goal saving chưa có ngày riêng.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/recurring-transactions` | List recurring | `?active=true` | `[{id,name,direction,amount,frequency,next_due_on,active}]` |
| POST | `/api/v1/recurring-transactions` | Tạo manual recurring | `{name,direction,amount,category_id,spending_type,frequency,day_of_month/day_of_week,next_due_on}` | Recurring read |
| PATCH | `/api/v1/recurring-transactions/{id}` | Sửa / pause | partial | Recurring read |
| DELETE | `/api/v1/recurring-transactions/{id}` | Deactivate | — | `204` |
| POST | `/api/v1/recurring-transactions/detect` | Chạy detection từ lịch sử | `{from_date,to_date}` | `{suggestions:[...]}` |
| POST | `/api/v1/recurring-transactions/suggestions/{suggestion_id}/confirm` | Xác nhận suggestion | `{name?,amount?,next_due_on?}` | Recurring read |
| POST | `/api/v1/recurring-transactions/{id}/create-transaction` | Tạo transaction từ khoản đến hạn | `{occurred_on?: date}` | Transaction read |
| GET | `/api/v1/calendar/month` | Sự kiện tháng | `?month=2026-10-01` | `{events:[{date,icon,label,amount,direction,kind,recurring_id}]}` |
| GET | `/api/v1/forecast` | Dự báo dòng tiền | `?days=30|60&start_date=...` | `{starting_balance,points,low_balance_warning}` |
| GET/PATCH | `/api/v1/settings/forecast` | Đọc/sửa starting balance + threshold | `{starting_balance,low_balance_threshold}` | Settings read |

Detection algorithm:
1. Group historical transactions by `(direction, category_id, spending_type)`.
2. Sort by `occurred_on`; find subsequences with at least 3 occurrences.
3. Similar amount: each amount within ±10% of median group amount.
4. Interval: weekly if median delta 7 ngày ±2; monthly if median delta 28–31 ngày hoặc same day-of-month ±3 ngày.
5. Confidence deterministic: `0.4 + amount_consistency*0.3 + interval_consistency*0.3`; only suggest nếu `confidence >= 0.75`.

`next_due_on`:
- Monthly day 31: dùng ngày cuối tháng nếu tháng không có 31 (Feb 28/29, Apr 30).
- Nếu computed date <= today, nhảy tới kỳ kế tiếp.
- Yearly giữ tháng/ngày từ `next_due_on`, leap day 29/02 fallback 28/02 năm không nhuận.

Forecast formula:
`projected_balance[d] = starting_balance + confirmed_actual_net_from_start_to_d + recurring_incomes_due_to_d - recurring_expenses_due_to_d - scheduled_goal_savings_to_d - average_daily_variable_spending * day_index`.
- `average_daily_variable_spending`: trung bình expense 30 ngày gần nhất, loại recurring/irregular; thiếu dữ liệu thì 0 và `insufficient_history=true`.
- `scheduled_goal_savings`: tổng suggested monthly saving của active goals, đặt vào `goal_saving_day_of_month`.

### 4.3 AI (nếu có)

Không gọi OpenAI trong Phase 12. "AI Financial Calendar" được hiện thực bằng deterministic detection/forecast để mọi số có thể test. Schema phục vụ Coach tương lai:

```python
class ForecastPoint(BaseModel):
    date: date
    projected_balance: int
    delta_income: int
    delta_expense: int
    delta_goal_saving: int

class ForecastOutput(BaseModel):
    starting_balance: int
    days: int
    points: list[ForecastPoint]
    low_balance_warning_day: date | None
    insufficient_history: bool
```

Nếu Phase 10 registry tồn tại, có thể đăng ký read-only tool `get_cashflow_forecast(days: int = 30)` ở cuối phase, nhưng không bắt buộc để Phase 12 Done.

### 4.4 Frontend

- Route `/calendar`:
  - `ForecastSettingsCard`: nhập starting balance và low-balance threshold.
  - `CalendarMonthView`: icon 💰 salary/income, 🏠 rent/housing, 💳 credit card, 📱 internet/utilities, 🎯 goal saving.
  - `UpcomingList`: khoản đến hạn trong 14 ngày, nút "Tạo giao dịch".
  - `RecurringSuggestionPanel`: patterns phát hiện, nút xác nhận/từ chối.
  - `ForecastLineChart`: đường projected balance 30/60 ngày, marker low-balance.
- Manual recurring form cho user thêm tiền nhà, internet, subscription.
- Khi bấm "Tạo giao dịch": gọi API tạo transaction, update `next_due_on`, hiển thị link sang `/transactions`.

## 5. Task breakdown

- [x] T1 Migration `recurring_transactions` + `transactions.recurring_id` + settings forecast seed
- [x] T2 Pydantic schemas recurring, detection suggestion, calendar event, forecast point
- [x] T3 `recurring_service` CRUD + `next_due_on` weekly/monthly/yearly (ngày 31, leap year)
- [x] T4 Detection algorithm từ lịch sử + suggestion confirm flow
- [x] T5 `forecast_service` daily projected balance 30/60 ngày + low-balance warning
- [x] T6 Routers `/api/v1/recurring-transactions`, `/api/v1/calendar/month`, `/api/v1/forecast`, `/settings/forecast`
- [x] T7 API/unit tests cho detection, next_due_on, forecast, create transaction source recurring
- [x] T8 UI `/calendar` month view + icons + upcoming list
- [x] T9 UI recurring manual form + suggestions confirm/dismiss
- [x] T10 UI forecast settings + line chart + warning state
- [x] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-12: calendar forecast`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend && alembic upgrade head && ruff check . && pytest
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run gen:api && npm run lint && npm run dev
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Rent housing 5.000.000 vào 2026-07-31, 2026-08-31, 2026-09-30 | Detection suggest monthly rent amount 5.000.000, day_of_month 31, confidence >= 0.75 |
| 2 | Amounts 1.000.000, 1.080.000, 920.000 cùng category monthly | Similar ±10% pass, suggested amount median 1.000.000 |
| 3 | Amounts 1.000.000, 1.250.000, 900.000 | Không suggest vì 1.250.000 vượt ±10% median |
| 4 | `next_due_on` monthly day 31 từ 2026-01-31 | Kỳ sau 2026-02-28; từ 2028-01-31 → 2028-02-29 |
| 5 | Weekly day_of_week Monday, today 2026-10-07 | next_due_on 2026-10-12 |
| 6 | Starting balance 12.000.000; salary +25.000.000 day 5; rent -5.000.000 day 1; goal -4.400.000 day 10; variable 200.000/day | Forecast ngày 10 = 25.600.000 |
| 7 | Low balance threshold 1.000.000; projected ngày 25 = 800.000 | `low_balance_warning_day=2026-10-25` |
| 8 | Create transaction từ recurring internet 300.000 due 2026-10-05 | Transaction `source="recurring"`, `recurring_id` set, next_due_on 2026-11-05 |

**Kịch bản thao tác UI**
1. Mở `/calendar`, nhập starting balance 12.000.000 và threshold 1.000.000.
2. Thêm recurring salary 25.000.000 ngày 5, rent 5.000.000 ngày 1, internet 300.000 ngày 5.
3. Calendar tháng hiển thị 💰 ngày 5, 🏠 ngày 1, 📱 ngày 5; goal saving hiển thị 🎯 ngày 10 nếu có active goal.
4. Bấm "Tạo giao dịch" ở internet → giao dịch xuất hiện ở `/transactions`, item chuyển sang kỳ sau.
5. Chạy detect từ lịch sử → panel đề xuất khoản monthly, user xác nhận và thấy recurring mới.
6. Chuyển forecast 30/60 ngày → chart cập nhật và marker low-balance nếu có.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` xanh không cần API key
- [x] Detection chỉ tạo suggestion, không tự tạo recurring khi user chưa xác nhận
- [x] Forecast formula có unit test với số VND cụ thể, không dùng float
- [x] `source='recurring'` và `recurring_id` được set khi tạo transaction từ due item
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [x] Commit `phase-12: calendar forecast`

## 8. Rủi ro / câu hỏi mở

- App chưa có tài khoản ngân hàng nên `starting_balance` do user nhập có thể lệch thực tế; UI phải ghi rõ đây là giả định forecast.
- Average daily variable spending từ lịch sử ngắn có thể nhiễu; response cần flag `insufficient_history`.
- Credit card payment chưa có entity riêng; Phase 12 map vào recurring expense category phù hợp và icon 💳 theo name/category heuristic.
- (Khi triển khai) "Chi biến đổi" loại giao dịch đã gắn khoản định kỳ và giao dịch **khớp** một khoản chi định kỳ đang bật (cùng danh mục, ±10%) — khoản nhà trả tay tháng trước không bị trừ 2 lần; nhưng một khoản chi khác cùng danh mục, số tiền gần bằng cũng bị loại (heuristic).
- (Khi triển khai) `start_date` = hôm nay: giao dịch đã ghi trong ngày được cộng **và** chi biến đổi trung bình vẫn trừ cho ngày đó (theo công thức plan, day_index bắt đầu 1) → ngày đầu có thể trừ hơi nhiều.
- (Khi triển khai) Kỳ định kỳ quá hạn chưa ghi (`next_due_on < start_date`) không vào dự báo (chỉ liệt kê `overdue_recurring`) — nếu user đã trả mà không bấm "Tạo giao dịch" thì khoản đó vẫn hiện quá hạn; nếu chưa trả thì dự báo đang lạc quan.
- (Khi triển khai) Kế hoạch để dành mục tiêu trong forecast / lịch tính tại **đầu tháng** của ngày bắt đầu (trừ phần đã góp trong tháng), nên có thể khác "gợi ý / tháng" ở `/goals` (tính tại hôm nay, giảm sau khi góp — xem Phase 11 § 8).

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22 (bắt đầu 2026-10-21)
- **Đã làm:**
  - **Migration** `20261022_a46a3e1b041a_calendar_forecast`: bảng `recurring_transactions` (CHECK amount / direction / spending_type / cặp direction–spending_type / frequency / `schedule` weekly ⇔ `day_of_week` 1–7, monthly·yearly ⇔ `day_of_month` 1–31; index `(active, next_due_on)`, `(category_id)`), cột `transactions.recurring_id` (FK `SET NULL` + index), seed `app_settings.forecast.low_balance_threshold = 1000000`, `forecast.goal_saving_day_of_month = 10`. ORM `models/recurring.py`, enum `RecurringFrequency`. Chi tiết: [data-model.md § Phase 12](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế).
  - **Deterministic, không AI:** `services/recurring_schedule` (hàm thuần: `next_occurrence` monthly ngày 31 → cuối tháng ngắn rồi về lại 31, weekly ISO, yearly 29/02 → 28/02; `is_occurrence`, `occurrences`, `due_status` (quá hạn / hôm nay / ≤ 14 ngày / còn xa), `calendar_icon` 💰 🏠 💳 📱 🔁 theo chiều / slug danh mục / từ khoá tên). `services/recurring_detection` (hàm thuần: gom `(direction, category, spending_type)` → cụm số tiền ±10% quanh trung vị (≥ 3 lần, nhiều cụm / nhóm) → nhịp weekly (trung vị 5–9 ngày) / monthly (28–31 ngày hoặc cùng ngày ±3 ở tháng liền kề) → `confidence = 0.4 + 0.3·amount + 0.3·interval ≥ 0.75` bằng `Fraction`; bỏ mẫu ngừng > 2 kỳ; suy `day_of_month` (31/07, 31/08, 30/09 → 31)). `services/recurring_service` (CRUD + validate lịch, phát hiện → lưu đề xuất ở `app_settings.recurring.suggestions`, xác nhận → tạo khoản `auto_detected` + gắn giao dịch lịch sử, bỏ qua → nhớ khoá mẫu, "Tạo giao dịch" → `source='recurring'`, `recurring_id`, `next_due_on` tiến 1 kỳ). `services/forecast_service` (settings `forecast.*`; hàm thuần `project_balance`, `goal_saving_schedule`, `variable_average`; `build_forecast`, `calendar_month`). `transaction_service.resolve_category/resolve_spending_type` thành public (dùng chung).
  - **API:** `GET/POST /recurring-transactions` (`?active=`, `?today=`; list `{items}`), `PATCH /recurring-transactions/{id}` (sửa / tạm dừng / bật lại), `DELETE …/{id}` (tắt, 204), `POST …/detect` (`{from_date?, to_date?}` mặc định 180 ngày tới hôm nay, tối đa 2 năm), `GET …/suggestions`, `POST …/suggestions/{id}/confirm` (201) / `…/dismiss` (204), `POST …/{id}/create-transaction` (`{occurred_on?, amount?}` → `{transaction, recurring, pyf_proposal}`), `GET /calendar/month?month=&today=` (`{month, today, events[{date, icon, label, amount, direction, kind: recurring|paid|goal_saving, recurring_id, transaction_id, overdue}], income_total, expense_total, goal_saving_total}`), `GET /forecast?days=1–90&start_date=&today=` (`ForecastOutput` plan § 4.3 + `opening_balance`, `min_balance(_day)`, `end_balance`, `average_daily_variable_spending`, `variable_history_days`, `monthly_goal_saving`, các tổng, `overdue_recurring`; point thêm `delta_variable`, `events`), `GET/PATCH /settings/forecast`. `TransactionRead` thêm `recurring_id`. Mã lỗi mới: `recurring_not_found`, `suggestion_not_found` (404), `invalid_schedule`, `next_due_on_mismatch` (422), `recurring_inactive` (409); dùng lại `category_*`, `income_spending_type`, `invalid_date_range`.
  - **Frontend:** route `/calendar` (`CalendarPage`, `?today=`): `ForecastLineChart` (Recharts, 30 / 60 ngày, ngưỡng + chấm ngày cảnh báo, ghi chú giả định / thiếu lịch sử / quá hạn), `ForecastSettingsCard`, `CalendarMonthView`, `UpcomingList` (Tạo giao dịch → link `/transactions`; lương → `PyfAllocationDialog`), `RecurringManager` + `RecurringFormDialog`, `RecurringSuggestionPanel`; `lib/calendar.ts` (nhãn, lưới tháng, `parseBalanceInput` cho 0 / âm), type mới trong `lib/api.ts`, nav "Lịch dòng tiền". `gen:api` chạy lại.
  - **Test:** **817 pass** (+108, không cần key): `tests/unit/test_recurring_schedule.py` (33 — test case 4, 5, yearly nhuận, icon), `tests/unit/test_recurring_detection.py` (15 — test case 1–3, weekly, lương, 2 mẫu cùng danh mục + nhiễu, nhịp lộn xộn, 2 lần, mẫu đã ngừng), `tests/unit/test_forecast_service.py` (16 — test case 6 (25.600.000), 7 (cảnh báo 2026-10-25, 800.000), giao dịch thật theo ngày, lịch để dành mục tiêu: đã góp trong tháng, tháng đến hạn, trần phần còn thiếu, quá hạn, kẹp ngày 31), `tests/api/test_recurring.py` (25 — CRUD / validate, test case 8, trả sớm / quá hạn, khoản tắt 409, lương → `pyf_proposal`, test case 1 qua API không tạo recurring, xác nhận gắn 3 giao dịch, bỏ qua được nhớ, mẫu đã có khoản thủ công), `tests/api/test_forecast.py` (19 — settings, test case 6 end-to-end qua DB (lịch sử chi tháng 9 có khoản bất thường + khoản nhà khớp bị loại → 200.000 / ngày), 60 ngày, test case 7, giao dịch sau ngày số dư, không trừ 2 lần sau "Tạo giao dịch", lịch tháng icon 🏠 💰 📱 🎯, paid / quá hạn).
  - **AI:** không gọi OpenAI trong Phase 12 (plan § 4.3). `pytest -m ai` chạy lại: **17/17 pass** (không đổi prompt).
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev, "No new upgrade operations detected"), `ruff check .`, `ruff format --check .`, `pytest` (817), `pytest -m ai` (17), `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh; `npm run start` → `/`, `/calendar`, `/calendar?today=2026-10-01`, `/transactions`, `/goals` trả 200. Smoke API + UI với **DB tạm `pfa_smoke`** (đã xoá; DB dev chỉ được migrate, không có dữ liệu Phase 12): số dư 12tr / ngưỡng 1tr; lương 25tr ngày 5, nhà 5tr ngày 1, internet 300k ngày 5 + goal Laptop (đã góp 8tr) → lịch 10/2026 🏠 01 · 💰📱 05 · 🎯 10 (4.400.000), dự báo 10/10 = 27.300.000; "Tạo giao dịch" internet → giao dịch "Định kỳ" ở `/transactions`, kỳ sau 05/11; "Tạo giao dịch" lương ở UI → dialog "Nhận lương" đề xuất 4.400.000; thêm "Thanh toán thẻ tín dụng" qua form → 💳; phát hiện Gym / Netflix / Cắt tóc → xác nhận (gắn 3 giao dịch) / bỏ qua (không đề xuất lại); 30 ↔ 60 ngày; số dư −2tr → cảnh báo "Ngày 01/11/2026 … 0 ₫" + chấm đỏ.
- **Lệch so với plan (và lý do):**
  - Đề xuất phát hiện **không có bảng**: lưu kết quả lần phát hiện gần nhất ở `app_settings.recurring.suggestions` (id ổn định = UUID5 của khoá mẫu) để `…/suggestions/{id}/confirm` của plan chạy được; thêm `GET …/suggestions`, `POST …/suggestions/{id}/dismiss` (UI "từ chối" § 4.4) và nhớ mẫu đã bỏ qua (`recurring.dismissed_suggestions`). Phát hiện bỏ giao dịch đã gắn khoản định kỳ và mẫu đã có khoản định kỳ đang bật (cùng chiều + danh mục + tần suất, ±10%). Xác nhận gắn `recurring_id` cho giao dịch lịch sử của mẫu (để chi biến đổi không đếm lại).
  - Thêm khái niệm **`starting_balance_on`** (`app_settings.forecast.starting_balance_on`): số dư user nhập tính tại đầu ngày đó; giao dịch thật từ ngày đó trở đi được cộng / trừ ("confirmed_actual_net" của công thức). `starting_balance` không seed (NULL = chưa nhập → dự báo từ 0 + `starting_balance_set=false`), cho phép 0 / âm.
  - `next_due_on` = kỳ kế tiếp **chưa ghi**; "Tạo giao dịch" chỉ tiến **một** kỳ (mỗi kỳ bị lỡ vẫn cần user xác nhận), mặc định `occurred_on = min(next_due_on, hôm nay)`, nhận thêm `amount` (hoá đơn dao động). Quy tắc "≤ hôm nay → nhảy kỳ sau" áp dụng khi tạo / đổi lịch không gửi `next_due_on` và khi bật lại khoản đã quá hạn. Response `create-transaction` = `{transaction, recurring, pyf_proposal}` thay vì chỉ Transaction (UI cần kỳ mới + Phase 11 PYF cho lương).
  - `yearly` lưu `day_of_month` (ngày gốc) + tháng của `next_due_on` để 29/02 quay lại được năm nhuận. `GET /recurring-transactions` trả `{items}` (quy ước repo) + `icon`, `days_until_due`, `due_status`, `transaction_count`, `category`. `days` của forecast nhận 1–90 (UI dùng 30 / 60).
  - Forecast: kỳ quá hạn chưa ghi không tính (liệt kê `overdue_recurring`); chi biến đổi = 30 ngày trước `start_date`, bỏ `irregular`, giao dịch đã gắn / khớp khoản chi định kỳ đang bật, chia số ngày có lịch sử (< 7 ngày → 0, < 30 → `insufficient_history`). Để dành mục tiêu: mỗi goal active = gợi ý / tháng tính tại đầu tháng của `start_date` (`goal_service.compute_progress`), tháng đầu trừ khoản đã góp trong tháng, không trích từ tháng đến hạn, tổng ≤ phần còn thiếu (handoff Phase 11). Lịch tháng chỉ hiện 🎯 từ tháng hiện tại trở đi.
  - Không đăng ký tool Coach `get_cashflow_forecast` (plan cho phép bỏ); schema `ForecastOutput` sẵn sàng.
- **Nợ kỹ thuật / TODO để lại:**
  - Xem § 8 (heuristic loại khoản chi khớp định kỳ, ngày đầu trừ chi biến đổi, kỳ quá hạn không tính, kế hoạch goal theo đầu tháng).
  - Xoá giao dịch tạo từ khoản định kỳ **không** lùi `next_due_on` (user sửa tay bằng PATCH `next_due_on`). Sửa giao dịch không đổi được `recurring_id`.
  - Đề xuất lưu "lần phát hiện gần nhất" (1 bản, không lịch sử); khoá bỏ qua gồm ngày neo — mẫu đổi ngày sẽ được đề xuất lại. Chưa phát hiện yearly.
  - Icon 💳 / 🏠 / 📱 theo từ khoá tiếng Việt không dấu + slug `housing` / `utilities`; chưa có entity thẻ tín dụng / tài khoản (câu hỏi mở xuyên suốt).
  - UI: chưa có xoá hẳn khoản định kỳ (DELETE = tắt, giống "Tạm dừng"); chưa sửa tên / số tiền trước khi xác nhận đề xuất (sửa sau ở bảng); chưa có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_recurring_schedule.py tests/unit/test_recurring_detection.py tests/unit/test_forecast_service.py tests/api/test_recurring.py tests/api/test_forecast.py -q)`
  - `curl -s -X PATCH "localhost:8000/api/v1/settings/forecast?today=2026-10-01" -H "Content-Type: application/json" -d '{"starting_balance":12000000,"low_balance_threshold":1000000}'`
  - `curl -s -X POST "localhost:8000/api/v1/recurring-transactions?today=2026-10-01" -H "Content-Type: application/json" -d '{"name":"Internet","direction":"expense","amount":300000,"category_id":"<utilities>","frequency":"monthly","day_of_month":5}'`
  - `curl -s -X POST "localhost:8000/api/v1/recurring-transactions/detect?today=2026-10-22" -H "Content-Type: application/json" -d '{}'`
  - `curl -s "localhost:8000/api/v1/forecast?days=60&today=2026-10-01"` · `curl -s "localhost:8000/api/v1/calendar/month?month=2026-10-01&today=2026-10-01"`
  - UI: `/calendar?today=2026-10-01`.
- **Gợi ý cho phase tiếp theo (Phase 13 — Receipt OCR):**
  - Giao dịch từ hoá đơn dùng `source='receipt'`; `transactions` đã có `recurring_id` (nullable) — `receipt_id` của Phase 13 thêm cùng kiểu (FK nullable + index, `SET NULL`/`RESTRICT` tuỳ quyết định). `TransactionRead` đang có `recurring_id` — thêm `receipt_id` tương tự.
  - Tạo giao dịch nội bộ (không qua `TransactionCreate` công khai) theo mẫu `recurring_service.create_transaction_from_recurring`: `transaction_service.resolve_category` / `resolve_spending_type` (public từ Phase 12) rồi `transaction_repository.add`, commit một lần; thu nhập → `goal_service.proposal_for_new_income` nếu cần PYF.
  - Hoá đơn định kỳ (điện, internet) sau khi xác nhận có thể gắn khoản định kỳ khớp (cùng danh mục, ±10% — `recurring_detection.within_tolerance`) — ngoài scope Phase 13, cân nhắc ghi nợ kỹ thuật.
  - DB dev: đã `alembic upgrade head` (có `recurring_transactions`, chưa có dữ liệu Phase 12). Postgres vẫn ở **port 5433**.
