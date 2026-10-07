# Phase 12 — Calendar / Forecast

| | |
|---|---|
| **ID** | `phase-12-calendar-forecast` |
| **Trạng thái** | Not started |
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

- [ ] T1 Migration `recurring_transactions` + `transactions.recurring_id` + settings forecast seed
- [ ] T2 Pydantic schemas recurring, detection suggestion, calendar event, forecast point
- [ ] T3 `recurring_service` CRUD + `next_due_on` weekly/monthly/yearly (ngày 31, leap year)
- [ ] T4 Detection algorithm từ lịch sử + suggestion confirm flow
- [ ] T5 `forecast_service` daily projected balance 30/60 ngày + low-balance warning
- [ ] T6 Routers `/api/v1/recurring-transactions`, `/api/v1/calendar/month`, `/api/v1/forecast`, `/settings/forecast`
- [ ] T7 API/unit tests cho detection, next_due_on, forecast, create transaction source recurring
- [ ] T8 UI `/calendar` month view + icons + upcoming list
- [ ] T9 UI recurring manual form + suggestions confirm/dismiss
- [ ] T10 UI forecast settings + line chart + warning state
- [ ] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-12: calendar forecast`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
cd backend; alembic upgrade head; ruff check .; pytest
uvicorn app.main:app --reload --port 8000
cd ..\frontend; npm run gen:api; npm run lint; npm run dev
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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` xanh không cần API key
- [ ] Detection chỉ tạo suggestion, không tự tạo recurring khi user chưa xác nhận
- [ ] Forecast formula có unit test với số VND cụ thể, không dùng float
- [ ] `source='recurring'` và `recurring_id` được set khi tạo transaction từ due item
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [ ] Commit `phase-12: calendar forecast`

## 8. Rủi ro / câu hỏi mở

- App chưa có tài khoản ngân hàng nên `starting_balance` do user nhập có thể lệch thực tế; UI phải ghi rõ đây là giả định forecast.
- Average daily variable spending từ lịch sử ngắn có thể nhiễu; response cần flag `insufficient_history`.
- Credit card payment chưa có entity riêng; Phase 12 map vào recurring expense category phù hợp và icon 💳 theo name/category heuristic.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
