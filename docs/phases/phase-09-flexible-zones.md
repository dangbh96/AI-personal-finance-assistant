# Phase 09 — Flexible Budget Zones

| | |
|---|---|
| **ID** | `phase-09-flexible-zones` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 5 phải Done |
| **Mở khoá** | Phase 18 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 5 (và Phase 8 nếu đã làm trước)
2. [glossary.md](../product/glossary.md) — `comfort_low`, `comfort_high`, `warning_threshold`, `zone`
3. [vision.md](../product/vision.md) — Budget linh hoạt, không áp chuẩn cứng
4. [brainstorm-original.md](../product/brainstorm-original.md) — mục 11 Flexible Budget
5. [budget-adjustment.md](../architecture/budget-adjustment.md) — công thức manual/auto/fallback và pro-rata
6. [data-model.md](../architecture/data-model.md) — cột mới trên `budget_allocations`
7. [backend-components.md](../architecture/backend-components.md) — `zone_service`
8. [frontend-structure.md](../architecture/frontend-structure.md) — `/budget` badge zones, `/budget/advice`
9. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu phase: Phase 5 đã có budget vs actual dashboard và aggregate actual theo allocation/category; Phase 4 có `budget_allocations.planned_amount`; transactions có `spending_type` để loại `irregular` khỏi lịch sử auto. Phase 8 có thể chưa làm hoặc đã làm; nếu đã làm, advisor phải dùng `comfort_high`.

## 2. Mục tiêu & giá trị cho user

Budget không còn là một con số cứng. Mỗi allocation có vùng 🟢 bình thường, 🟡 chú ý, 🔴 cần xem lại, tính thủ công hoặc tự động từ 3–6 tháng lịch sử của chính user. User nhìn `/budget` biết khoản nào thật sự cần chú ý, tránh cảm giác "vượt 1 đồng cũng sai".

## 3. Scope

**In scope**
- Thêm cột `comfort_low`, `comfort_high`, `warning_threshold`, `zone_mode` trên `budget_allocations`.
- `zone_service` tính zone theo công thức trong [budget-adjustment.md](../architecture/budget-adjustment.md).
- Auto mode loại giao dịch `irregular`, dùng lịch sử 3–6 tháng gần nhất, fallback percentages khi thiếu dữ liệu.
- Pro-rata early warning cho tháng đang chạy.
- API đọc/cập nhật zone settings và recalculate.
- UI `/budget`: badge 🟢🟡🔴, tooltip giải thích ngưỡng và pro-rata.
- Nếu Phase 8 đã có, `advisor_rules` dùng `comfort_high` thay `planned_amount` để xác định vượt.

**Out of scope**
- Tạo `budget_advice` mới (Phase 8).
- Forecast cashflow/calendar (Phase 12).
- AI narrative mới; phase này deterministic.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Alter bảng `budget_allocations`:
- `comfort_low BIGINT NULL`
- `comfort_high BIGINT NULL`
- `warning_threshold BIGINT NULL`
- `zone_mode TEXT NOT NULL DEFAULT 'auto' CHECK (zone_mode IN ('manual','auto'))`

Ràng buộc service-level:
- `comfort_low <= comfort_high <= warning_threshold`.
- Tất cả số tiền là integer VND; công thức auto/fallback giữ đúng theo [budget-adjustment.md](../architecture/budget-adjustment.md). Nếu công thức tạo `.5`, làm tròn tới đồng gần nhất.
- Manual mode bắt buộc đủ 3 ngưỡng; auto mode có thể lưu ngưỡng đã tính để cache, nhưng recalculate phải idempotent.

Không tạo bảng `budget_zones`; data model hiện tại thiết kế cột trực tiếp trên `budget_allocations`.

### 4.2 Backend (services, API)

`services/zone_service.py`:
- `calculate_auto_zone(allocation, month)`:
  - Lấy actual category/jar 3–6 tháng trước month.
  - Loại mọi transaction có `spending_type='irregular'`.
  - Nếu có >= 3 tháng: `comfort_high = max(planned, mean + 0.5*std)`, `warning_threshold = max(planned*1.1, mean + 1*std)`, `comfort_low = planned*0.875`.
  - Nếu thiếu dữ liệu: `comfort_low = 0.875*planned`, `comfort_high = 1.125*planned`, `warning_threshold = 1.25*planned`.
  - Công thức giữ đúng như tài liệu: không làm tròn 100.000đ. Vì DB lưu integer VND, giá trị lẻ `.5` được làm tròn tới đồng gần nhất bằng helper chung, ví dụ `4.081.649,5` → `4.081.650`.
- `get_zone_status(actual, allocation, today)`:
  - 🟢 `normal` nếu `actual <= comfort_high`.
  - 🟡 `attention` nếu `comfort_high < actual <= warning_threshold`.
  - 🔴 `review_needed` nếu `actual > warning_threshold`.
  - Pro-rata early warning: nếu tháng hiện tại và `actual > planned * elapsed_days / days_in_month` đáng kể, trả thêm `early_warning=true` và message, không đổi zone chính nếu vẫn dưới `comfort_high`.

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/budgets/{budget_id}/zones` | Lấy ngưỡng + status mọi allocation | `?today=2026-10-15` | `{items:[BudgetZoneRead]}` |
| PATCH | `/api/v1/budget-allocations/{id}/zone` | Cập nhật manual/auto mode | `{zone_mode, comfort_low, comfort_high, warning_threshold}` | `BudgetAllocationRead` |
| POST | `/api/v1/budgets/{budget_id}/zones/recalculate` | Recalculate auto zones | `{allocation_ids:null}` | `{items:[BudgetZoneRead]}` |
| GET | `/api/v1/budgets/{budget_id}/actuals` | Mở rộng response Phase 5 thêm zone | — | Budget vs Actual rows có `zone` |

Nếu Phase 8 tồn tại: sửa `advisor_rules` để `limit = allocation.comfort_high or allocation.planned_amount`.

### 4.3 AI

Không thêm OpenAI call trong Phase 9. `OPENAI_MODEL_FAST`/`OPENAI_MODEL_SMART` không được dùng ở `zone_service`; mọi ngưỡng và badge deterministic.

Nếu Phase 8 đã có AI explanation, evidence đưa sang advisor được mở rộng như sau để AI chỉ diễn giải số đã tính:

```python
from typing import Literal
from pydantic import BaseModel

class ZoneEvidence(BaseModel):
    zone_mode: Literal["manual", "auto"]
    planned_amount: int
    comfort_low: int
    comfort_high: int
    warning_threshold: int
    actual_amount: int
    zone: Literal["normal", "attention", "review_needed"]
    early_warning: bool
```

Prompt/guardrail không đổi so với Phase 8:
- 3 tầng Observation → Explanation → Action nếu explanation được gọi ở advisor.
- Cấm "bạn tiêu quá nhiều", "lãng phí", "bạn phải", "bạn nên ngay lập tức".
- Mọi số trong narrative/advice phải có trong metrics/evidence.
- AI không được đề xuất ngưỡng mới; ngưỡng do `zone_service` tính hoặc user nhập.

### 4.4 Frontend

- `/budget` bổ sung cột badge zone:
  - 🟢 `normal`: "Trong vùng thoải mái"
  - 🟡 `attention`: "Đã vượt vùng thoải mái"
  - 🔴 `review_needed`: "Vượt ngưỡng cảnh báo"
- `ZoneBadge`, `ZoneTooltip`, `ZoneSettingsDialog`.
- Dialog cho manual mode: nhập Target (planned đã có), Comfort low/high, Warning threshold; validate ngay trên client và backend.
- Auto mode: hiển thị "Tính từ 3–6 tháng gần nhất, không tính khoản bất thường".
- Pro-rata warning hiển thị dòng phụ: "Đã dùng 80% budget khi mới qua 50% tháng".

## 5. Task breakdown

- [x] T1 Migration thêm `comfort_low`, `comfort_high`, `warning_threshold`, `zone_mode` vào `budget_allocations`
- [x] T2 Implement `zone_service.calculate_auto_zone` với 3–6 tháng history, exclude irregular, fallback percentages
- [x] T3 Implement `get_zone_status` + pro-rata early warning
- [x] T4 API zones: get, patch manual/auto, recalculate, mở rộng budget actual rows
- [x] T5 Cập nhật `advisor_rules` Phase 8 (nếu có) để dùng `comfort_high` khi present
- [x] T6 Unit tests mean/std/fallback/manual/pro-rata bằng số cụ thể
- [x] T7 API tests validate ngưỡng manual và recalculate idempotent
- [x] T8 Frontend `/budget` badge 🟢🟡🔴 + tooltip + settings dialog
- [x] T9 Smoke UI budget dashboard với auto và manual allocations
- [x] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-09: flexible budget zones`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_zone_service.py tests/api/test_budget_zones.py

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest deterministic)**
| # | Input | Kỳ vọng |
|---|---|---|
| 1 | Auto food planned 4.000.000; non-irregular history 3.800.000, 4.200.000, 4.000.000 | mean 4.000.000, population std ≈ 163.299; `comfort_high=4.081.650`, `warning_threshold=4.400.000`, `comfort_low=3.500.000` |
| 2 | Auto shopping planned 2.000.000; history raw 1.800.000 + laptop irregular 6.500.000, 2.100.000, 2.000.000 | laptop excluded; mean ≈ 1.966.667, population std ≈ 124.722; `comfort_high=2.029.028`, `warning_threshold=2.200.000`, `comfort_low=1.750.000` |
| 3 | Thiếu history, transport planned 1.000.000 | `comfort_low=875000`, `comfort_high=1125000`, `warning_threshold=1250000` |
| 4 | Manual entertainment low 800.000, high 1.200.000, warning 1.500.000; actual 1.300.000 | zone `attention` |
| 5 | Manual invalid low 1.300.000, high 1.200.000 | 422 |
| 6 | Food high 4.100.000, warning 4.200.000; actual 4.250.000 | zone `review_needed` |
| 7 | Tháng 10 có 31 ngày, today 2026-10-15, planned 4.000.000, actual 3.200.000 | elapsed ratio 15/31; pro-rata expected ≈ 1.935.484; `early_warning=true` |
| 8 | Phase 8 advisor với comfort_high 4.500.000, planned 4.000.000, actual 4.300.000 | verdict `on_track` |

**Kịch bản thao tác UI**
1. Mở `/budget` sau recalculate → mỗi allocation có badge 🟢/🟡/🔴 và tooltip ngưỡng.
2. Chuyển Food sang manual: low 3.500.000, high 4.500.000, warning 5.000.000 → lưu, badge tính lại.
3. Chuyển lại auto → ngưỡng lấy theo lịch sử, label "Auto".
4. Ở giữa tháng, allocation dùng nhanh hơn pro-rata → thấy warning phụ nhưng zone chính vẫn theo comfort/warning.

## 7. Definition of Done

- [x] Công thức manual/auto/fallback khớp `budget-adjustment.md`
- [x] Irregular transactions bị loại khỏi auto history
- [x] Pro-rata early warning có test
- [x] `/budget` hiển thị badge và không tự tính ngưỡng ở frontend
- [x] P8 advisor dùng `comfort_high` khi có (nếu P8 đã implement)
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [x] Commit `phase-09: ...`

## 8. Rủi ro / câu hỏi mở

- `budget_allocations` theo jar không có `category_id` có thể khó lấy history; nếu Phase 4 chưa có mapping jar-category, chỉ auto cho category allocation và yêu cầu manual cho jar.
  - **Đã giải quyết:** Phase 4 có `app_settings.budget_jar_category_map` → auto dùng chung `budget_service.allocation_scope` cho dòng danh mục / hũ / nhóm (dòng nhóm khớp theo `spending_type`). Dòng nhóm `irregular` luôn dùng % dự phòng (bỏ khoản bất thường thì không còn gì để học).
- Auto mode "hấp thụ" chi vượt ổn định: Ăn uống 4,4 / 4,6 / 4,5 triệu với planned 4 triệu → `comfort_high` ≈ 4,54 triệu nên advisor (Phase 8) thường ra `on_track` thay vì `adjust_budget` khi dòng đã tính vùng. Đúng tinh thần "dựa trên dữ liệu của chính user" nhưng có thể che mất tín hiệu "budget đặt thấp" — cân nhắc ở Phase 18 (vd. advisor xét `planned` cho bước "3 tháng đều vượt", hoặc hiển thị song song).
- Pro-rata tuyến tính vẫn báo sớm cho khoản cố định trả đầu tháng (tiền nhà 100% ngày 1) — cần lịch khoản định kỳ (Phase 12).

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:** 2026-10-22
- **Đã làm:**
  - **Migration** `20261022_b151e98b6b47_flexible_budget_zones`: `budget_allocations` thêm `comfort_low` / `comfort_high` / `warning_threshold` (BIGINT NULL) + `zone_mode TEXT NOT NULL DEFAULT 'auto'` và CHECK `ck_budget_allocations_zone_mode` (tạo tay vì autogenerate không bắt CHECK). ORM + enum `ZoneMode`, `ZoneStatus` (`models/enums.py`).
  - **Deterministic** `services/zone_service.py` (không AI): hàm thuần `history_stats` (mean chính xác + population std Decimal 40 chữ số), `fallback_thresholds`, `history_thresholds`, `calculate_auto_zone_from_history` (6 tháng **trước** tháng ngân sách, tháng có dữ liệu = có giao dịch chi trong phạm vi, giá trị không tính `irregular`, ≥ 3 tháng → công thức lịch sử, tối đa 6 tháng gần nhất; thiếu / nhóm `irregular` → 0,875 / 1,125 / 1,25 × planned; làm tròn tới đồng), `validate_manual_thresholds`, `zone_for`, `pro_rata` (dung sai 10 điểm % như Phase 5; message "Đã dùng 80% ngân sách khi mới qua 48,4% tháng"), `get_zone_status`, `allocation_zone`, `zone_evidence`, `auto_detail` (cách tính + `stale`); hàm DB `load_histories` (6 aggregate / budget), `calculate_auto_zone`, `update_zone`, `recalculate_auto_zones`. `money.elapsed_days` (dùng chung với `analytics_service.month_progress`).
  - **Tích hợp:** `analytics_service` gắn `zone` vào mỗi `AllocationStatusRead` (savings → `null`) và thêm `get_budget_zones`; `budget_advice_service` dùng `allocation.comfort_high` (bỏ `getattr`) + `ZoneEvidence` → `BudgetAdviceEvidence.zone` (mặc định `null`, evidence cũ vẫn đọc được); `budget_service._set_allocations` giữ vùng theo dòng cùng danh mục / hũ (manual luôn giữ; cache auto giữ khi planned không đổi; copy tháng → bỏ cache auto), `set_allocation_planned` xoá cache auto khi planned đổi.
  - **API:** `GET /budgets/{id}/zones?today=` → `BudgetZoneList` (`progress`, `items[BudgetZoneRead]`: ngưỡng, `calculated`, `zone`, `early_warning(_message)`, planned/actual/used %/`expected_to_date`, `auto{basis, fallback_reason, history[…], history_months, mean, std, suggested, stale}`); `POST /budgets/{id}/zones/recalculate?today=` body `{allocation_ids: null | [...]}` (tuỳ chọn) → cùng response; `PATCH /budget-allocations/{id}/zone` `{zone_mode, comfort_low, comfort_high, warning_threshold}` → `BudgetAllocationRead` (thêm 4 cột vùng); `GET /budgets/{id}/status` (và `top_over` của month-summary) có thêm `zone`. Mã lỗi: `invalid_zone_thresholds`, `zone_thresholds_required`, `zone_thresholds_not_allowed`, `allocation_not_tracked` (422); `allocation_not_found`, `budget_not_found` (404); `budget_closed` (409).
  - **Frontend:** `components/ui/tooltip.tsx` (shadcn CLI), `lib/zones.ts` (nhãn/màu/icon), `ZoneBadge` / `ZoneTooltip` / `EarlyWarningLine` (`zone-badge.tsx`), `ZoneSettingsDialog` (Auto / Thủ công, validate client, PATCH), `BudgetVsActualTable` thêm cột **Vùng** + dòng cảnh báo sớm, `BudgetTracking` tải `/zones`, khung nhắc + nút "Tính vùng tự động" khi có dòng auto chưa tính / ngưỡng cũ (ẩn nút khi ngân sách đã đóng). `gen:api` chạy lại.
  - **Test:** 589 pass (+42): `tests/unit/test_zone_service.py` (25 — test case 1–8 bằng số cụ thể, tách irregular theo phạm vi, dòng nhóm theo spending_type, tối đa 6 tháng / tháng trống, comfort_high ≥ planned, idempotent, fallback làm tròn half-up, nhóm irregular, biên zone, biên pro-rata, chưa tính vùng, savings, `stale`, advisor có / không vùng), `tests/api/test_budget_zones.py` (17 — GET trước khi tính, recalculate case 1–3 + idempotent + chọn dòng / bỏ qua manual + lỗi, PATCH case 4–6 + auto tính lại + lỗi, budget đóng 409, case 7 pro-rata, `zone` trong status, giữ / bỏ vùng khi PATCH budget / copy tháng / `set_allocation_planned`, case 8 advisor qua API).
  - **Golden AI** (không có golden riêng cho phase — không thêm lời gọi AI): chạy lại `tests/ai_golden/test_budget_advice_explanation.py` vì evidence thêm `zone` → **4/4 pass** (`gpt-4o-mini`).
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev), `ruff check .`, `ruff format --check .`, `pytest` (589), `pytest tests/unit/test_zone_service.py tests/api/test_budget_zones.py`, `pytest -m ai tests/ai_golden/test_budget_advice_explanation.py`, `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh; `npm run start` → `/`, `/budget?month=2026-10&today=2026-10-15`, `/budget/advice`, `/budget/new`, `/transactions`, `/reviews/monthly/2026-10` trả 200. Smoke API + kịch bản UI mục 6 trên trình duyệt với **DB tạm `pfa_smoke`** (seed_demo 06–09 + seed_scenario 10/2026, đã xoá sau khi chạy; DB dev chỉ được migrate, không bị ghi vùng): recalculate 2 lần cho kết quả giống hệt; PATCH manual sai → 422; bảng có badge 🟢/🔴 + tooltip ngưỡng; dialog Ăn uống: client chặn "mức trên > ngưỡng cảnh báo", lưu thủ công 3,5tr / 4,2tr / 5tr → badge 🟡; chuyển lại Auto → tooltip "Vùng linh hoạt · Auto … Dựa trên 4 tháng"; đổi planned Mua sắm → "1 dòng chưa có vùng" → "Tính vùng tự động" → 🔴; ngày 15/10 mọi dòng có dòng phụ "Đã dùng …% ngân sách khi mới qua 48,4% tháng" trong khi zone giữ theo ngưỡng; bấm badge / dialog không mở drill-down; advisor tháng 10 trên DB tạm dùng `comfort_high` (`comfort_high_used = true`, `evidence.zone`).
- **Lệch so với plan (và lý do):**
  - Plan ghi `GET /budgets/{id}/actuals`; thực tế Phase 5 là `GET /budgets/{id}/status` → thêm `zone` vào đó (không tạo endpoint mới trùng chức năng).
  - Ngưỡng auto **không** tự tính khi tạo / copy budget hay khi đọc: chỉ lưu khi user bấm "Tính vùng tự động" / chuyển sang auto (dòng mới = `auto` + ngưỡng NULL = "chưa có zone"). Lý do: sơ đồ advisor "comfort_high (hoặc planned nếu chưa có zone)" và giữ nguyên hành vi Phase 8 (4 case chuẩn) cho tới khi user chủ động bật vùng; GET không ghi DB. `GET /zones` vẫn trả `auto.suggested` để UI giải thích trước khi tính.
  - Định nghĩa thêm: "3–6 tháng" = 6 tháng trước tháng ngân sách, cần ≥ 3 tháng có giao dịch trong phạm vi (tháng trống bị bỏ, không tính là 0); dòng nhóm `irregular` luôn % dự phòng; early warning = chênh > 10 điểm % (như `pace_status`), chỉ khi tháng đang chạy, độc lập với zone (vẫn hiện khi đã 🟡/🔴); `recalculate` bỏ qua dòng manual (kể cả khi được liệt kê) và nhận `today` (query) để trả status.
  - Response thêm `calculated`, `early_warning_message`, `expected_to_date`, `auto{…, stale}`; PATCH auto không nhận ngưỡng (422 `zone_thresholds_not_allowed`); ngân sách đã đóng không chỉnh / tính vùng (409, như sửa budget Phase 4).
  - Thêm `ZoneEvidence` vào evidence advisor (§ 4.3) — prompt advisor không đổi (v1), evidence JSON có thêm khoá `zone`.
  - Thêm UI component `tooltip` (shadcn) — repo chưa có.
- **Nợ kỹ thuật / TODO để lại:**
  - Ngưỡng auto không tự cập nhật khi giao dịch lịch sử đổi — UI báo `stale` + nút tính lại; chưa có job tự tính đầu tháng.
  - Advisor đọc ngưỡng đã lưu, kể cả khi `stale`. Advice `open` đã tạo không tự tính lại khi đổi vùng (bấm "Tính lại tư vấn đang chờ").
  - Mục 8: auto hấp thụ chi vượt ổn định; pro-rata tuyến tính với khoản cố định đầu tháng.
  - Trang chủ / review tháng / `/budget/advice` chưa hiển thị badge vùng (chỉ `/budget`). `EvidenceTable` chưa hiện `evidence.zone` (chỉ dùng `comfort_high` như Phase 8).
  - Tooltip chỉ mở bằng hover / focus (không có trên cảm ứng). Chưa có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_zone_service.py tests/api/test_budget_zones.py -q)`
  - `curl -s "localhost:8000/api/v1/budgets/<id>/zones?today=2026-10-15"`
  - `curl -s -X POST "localhost:8000/api/v1/budgets/<id>/zones/recalculate?today=2026-10-31" -H "Content-Type: application/json" -d '{"allocation_ids":null}'`
  - `curl -s -X PATCH localhost:8000/api/v1/budget-allocations/<id>/zone -H "Content-Type: application/json" -d '{"zone_mode":"manual","comfort_low":3500000,"comfort_high":4500000,"warning_threshold":5000000}'`
  - UI: `/budget?month=2026-10&today=2026-10-15` (tab Theo dõi, cột Vùng).
- **Gợi ý cho phase tiếp theo (Phase 10 — Financial Coach):**
  - Tool read-only cho coach: `analytics_service.get_budget_zones(db, budget_id, today)` (zone + ngưỡng + cảnh báo sớm + cách tính) và `get_budget_status` (đã có `zone` từng dòng) — coach chỉ diễn giải, không đề xuất ngưỡng mới (ngưỡng do `zone_service` / user).
  - Ghi vùng (PATCH zone / recalculate) là thao tác ghi → nếu coach gợi ý, phải qua xác nhận của user (ADR-005).
  - Dòng `zone = null` nghĩa là chưa tính vùng — coach nên nói "chưa đặt vùng" thay vì suy ra 🟢.
  - DB dev: đã `alembic upgrade head` (cột vùng tồn tại, mọi dòng `auto` + NULL).
