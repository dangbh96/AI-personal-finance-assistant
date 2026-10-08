# Phase 09 — Flexible Budget Zones

| | |
|---|---|
| **ID** | `phase-09-flexible-zones` |
| **Trạng thái** | Not started |
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

- [ ] T1 Migration thêm `comfort_low`, `comfort_high`, `warning_threshold`, `zone_mode` vào `budget_allocations`
- [ ] T2 Implement `zone_service.calculate_auto_zone` với 3–6 tháng history, exclude irregular, fallback percentages
- [ ] T3 Implement `get_zone_status` + pro-rata early warning
- [ ] T4 API zones: get, patch manual/auto, recalculate, mở rộng budget actual rows
- [ ] T5 Cập nhật `advisor_rules` Phase 8 (nếu có) để dùng `comfort_high` khi present
- [ ] T6 Unit tests mean/std/fallback/manual/pro-rata bằng số cụ thể
- [ ] T7 API tests validate ngưỡng manual và recalculate idempotent
- [ ] T8 Frontend `/budget` badge 🟢🟡🔴 + tooltip + settings dialog
- [ ] T9 Smoke UI budget dashboard với auto và manual allocations
- [ ] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-09: flexible budget zones`

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

- [ ] Công thức manual/auto/fallback khớp `budget-adjustment.md`
- [ ] Irregular transactions bị loại khỏi auto history
- [ ] Pro-rata early warning có test
- [ ] `/budget` hiển thị badge và không tự tính ngưỡng ở frontend
- [ ] P8 advisor dùng `comfort_high` khi có (nếu P8 đã implement)
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-09: ...`

## 8. Rủi ro / câu hỏi mở

- `budget_allocations` theo jar không có `category_id` có thể khó lấy history; nếu Phase 4 chưa có mapping jar-category, chỉ auto cho category allocation và yêu cầu manual cho jar.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
