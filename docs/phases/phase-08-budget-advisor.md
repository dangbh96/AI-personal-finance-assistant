# Phase 08 — Budget Adjustment Advisor

| | |
|---|---|
| **ID** | `phase-08-budget-advisor` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 7 phải Done |
| **Mở khoá** | Phase 10 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 7](./phase-07-monthly-review.md)
2. [glossary.md](../product/glossary.md) — `BudgetAdvice`, `verdict`
3. [vision.md](../product/vision.md) — Actual > Budget không mặc định sửa budget
4. [brainstorm-original.md](../product/brainstorm-original.md) — mục 10 Budget Adjustment
5. [budget-adjustment.md](../architecture/budget-adjustment.md) — decision tree và 4 test case chuẩn
6. [data-model.md](../architecture/data-model.md) — `budget_advice`
7. [backend-components.md](../architecture/backend-components.md) — `advisor_rules`, `budget_service`
8. [ai-architecture.md](../architecture/ai-architecture.md) — AI chỉ viết explanation từ evidence
9. [frontend-structure.md](../architecture/frontend-structure.md) — route `/budget/advice`
10. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu phase: Phase 7 đã có monthly review/metrics; Phase 5 có budget vs actual theo allocation/category; Phase 4 có `budget_service` tạo/sửa budget tháng; Phase 6/7 có OpenAI client + guardrail narrative.

## 2. Mục tiêu & giá trị cho user

Khi một khoản vượt budget, app phân biệt rõ: budget đặt quá thấp, hành vi cần xem lại, hay khoản bất thường một lần. User nhận được evidence và lựa chọn **Accept** để áp dụng planned amount mới cho tháng sau hoặc **Dismiss** để bỏ qua. AI không quyết định verdict; AI chỉ diễn giải bằng giọng trung lập.

## 3. Scope

**In scope**
- Implement đúng decision tree trong [budget-adjustment.md](../architecture/budget-adjustment.md).
- Thresholds lưu trong `app_settings`: `one_off_share_threshold=0.6`, `stable_cv_threshold=0.15`, `min_history_months=3`, `budget_rounding_step=100000`.
- Bảng `budget_advice`.
- Deterministic `services/advisor_rules.py` trả verdict/evidence/proposed amount.
- AI structured output chỉ viết `explanation` từ evidence đã tính.
- API generate advice theo month/allocation; accept áp dụng `proposed_planned_amount` vào budget tháng sau qua `budget_service`, cần user confirmation; dismiss.
- UI `/budget/advice`; monthly review có trigger tạo advice.

**Out of scope**
- Flexible zones (Phase 9), nhưng nếu cột zone đã tồn tại thì Phase 8 ưu tiên `comfort_high` khi đánh giá vượt.
- Coach chat (Phase 10).
- Tự động sửa budget mà không có user confirmation.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Tạo bảng `budget_advice`: `id UUID PK`, `user_id UUID NULL`, `budget_allocation_id UUID NOT NULL FK`, `month DATE NOT NULL`, `verdict TEXT NOT NULL CHECK (verdict IN ('adjust_budget','adjust_behavior','one_off','on_track'))`, `evidence JSONB NOT NULL`, `explanation TEXT NOT NULL`, `status TEXT DEFAULT 'open' CHECK (status IN ('open','accepted','dismissed'))`, timestamps.
- Unique partial hoặc service rule: chỉ 1 advice `open` trên `(budget_allocation_id, month)`.
- `evidence` chứa `planned_amount`, `actual_amount`, `comfort_high_used`, `over_amount`, `history_actuals`, `cv`, `single_transaction_share`, `irregular_transaction`, `proposed_planned_amount`.

Seed/ensure `app_settings` keys:
```json
{
  "budget_advisor": {
    "one_off_share_threshold": 0.6,
    "stable_cv_threshold": 0.15,
    "min_history_months": 3,
    "budget_rounding_step": 100000
  }
}
```

### 4.2 Backend (services, API)

Decision tree bắt buộc:
1. Nếu `actual <= comfort_high` (hoặc `planned_amount` nếu chưa có zone) → `on_track`.
2. Nếu có giao dịch `irregular` hoặc một giao dịch đơn lẻ chiếm `>= 60%` phần vượt → `one_off`.
3. Nếu lịch sử `< 3` tháng → `adjust_behavior`.
4. Nếu 3 tháng gần nhất đều vượt planned và CV actual `<= 15%` → `adjust_budget`, proposed = median(3 tháng), làm tròn 100.000đ.
5. Còn lại → `adjust_behavior`.

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/budget/advice` | Danh sách advice | `?month=2026-10-01&status=open` | `{items:[BudgetAdviceRead]}` |
| POST | `/api/v1/budget/advice/generate` | Generate advice cho tháng | `{month:"2026-10-01", allocation_id:null}` | `{items:[BudgetAdviceRead]}` |
| POST | `/api/v1/budget/advice/{id}/accept` | User xác nhận áp dụng | `{confirm:true, target_month:"2026-11-01"}` | `{advice, updated_allocation}` |
| POST | `/api/v1/budget/advice/{id}/dismiss` | Bỏ qua advice | `{reason:"one-off already handled"}` | `BudgetAdviceRead(status="dismissed")` |
| GET | `/api/v1/budget/advice/settings` | Xem thresholds | — | `budget_advisor` settings |
| PATCH | `/api/v1/budget/advice/settings` | Sửa thresholds | JSON subset | settings mới |

Accept action:
- Chỉ hợp lệ cho `verdict="adjust_budget"` và `status="open"`.
- Gọi `budget_service.ensure_next_month_budget(target_month)` rồi cập nhật allocation cùng category/jar bằng `proposed_planned_amount`.
- Nếu budget tháng sau chưa tồn tại, tạo draft từ tháng hiện tại trước rồi sửa allocation.

### 4.3 AI

`advisor_rules` quyết định verdict/evidence. AI chỉ viết explanation ngắn, từ evidence; nếu AI lỗi dùng template deterministic.

Model: `OPENAI_MODEL_FAST` mặc định cho explanation; `OPENAI_MODEL_SMART` không cần dùng trừ khi muốn wording tốt hơn và có cấu hình riêng.

```python
from typing import Literal
from pydantic import BaseModel, Field

class BudgetAdviceExplanation(BaseModel):
    observation: str = Field(description="Nêu planned/actual/variance từ evidence")
    explanation: str = Field(description="Giải thích verdict, không thêm số ngoài evidence")
    action: str | None = Field(description="Gợi ý có điều kiện; accept/dismiss do user quyết")
    tone: Literal["neutral", "supportive"]
```

Prompt outline:
- Input: verdict deterministic + evidence JSON + allowed numbers.
- Với `adjust_budget`: giải thích planned hiện thấp hơn lịch sử ổn định.
- Với `one_off`: chỉ rõ giao dịch ngoại lệ; không bảo tăng budget.
- Với `adjust_behavior`: nói chưa đủ ổn định để kết luận budget sai.
- Với `on_track`: nói allocation đang trong kế hoạch.

Guardrails:
- 3 tầng Observation → Explanation → Action.
- Banned phrases: "bạn tiêu quá nhiều", "lãng phí", "bạn phải", "bạn nên ngay lập tức", "sai lầm".
- Mọi số trong explanation phải có trong `evidence`.
- Không được ghi "tôi đã điều chỉnh budget"; chỉ "nếu bạn xác nhận, app sẽ...".

### 4.4 Frontend

- Route `/budget/advice`.
- Components: `BudgetAdviceList`, `AdviceCard`, `EvidenceTable`, `AcceptAdviceDialog`, `DismissButton`, `AdvisorSettingsPanel` (ẩn sau collapsible).
- Monthly review CTA gọi `POST /budget/advice/generate` cho tháng đó rồi điều hướng `/budget/advice?month=...`.
- Card hiển thị badge verdict:
  - `adjust_budget`: "Budget có thể thấp hơn thực tế"
  - `one_off`: "Khoản bất thường một lần"
  - `adjust_behavior`: "Nên xem lại hành vi/nhịp chi"
  - `on_track`: "Đang trong kế hoạch"

## 5. Task breakdown

- [ ] T1 Migration `budget_advice` + seed `app_settings.budget_advisor`
- [ ] T2 Implement `services/advisor_rules.py` đúng decision tree + helper median/CV/rounding
- [ ] T3 Query evidence từ budget actual, transactions, history 3 tháng; ưu tiên `comfort_high` nếu có
- [ ] T4 AI explanation wrapper + template fallback + guardrail số/banned phrases
- [ ] T5 Router `/api/v1/budget/advice*` generate/list/accept/dismiss/settings
- [ ] T6 Unit tests 4 standard cases từ `budget-adjustment.md`
- [ ] T7 API tests accept/dismiss + user confirmation required
- [ ] T8 Frontend `/budget/advice` + monthly review trigger
- [ ] T9 Golden AI tests `@pytest.mark.ai` cho explanation trung lập
- [ ] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-08: budget advisor`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_advisor_rules.py tests/api/test_budget_advice.py
pytest -m ai tests/ai_golden/test_budget_advice_explanation.py

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest deterministic — chuẩn bắt buộc)**
| # | Input | Kỳ vọng |
|---|---|---|
| 1 | Food planned 4.000.000; actual 3 tháng: 4.400.000 / 4.600.000 / 4.500.000 | `verdict=adjust_budget`, `proposed_planned_amount=4500000` |
| 2 | Shopping planned 2.000.000; actual 8.000.000; 1 transaction laptop 6.500.000 `irregular` | `verdict=one_off`, evidence chỉ ra laptop, không proposed amount |
| 3 | Entertainment planned 1.000.000; actual 1.400.000; history 800.000 / 1.600.000 / 1.400.000 | `verdict=adjust_behavior` |
| 4 | Transport planned 1.000.000; actual 700.000 | `verdict=on_track` |
| 5 | Food planned 4.000.000; actual 4.300.000; thiếu history (2 tháng) | `adjust_behavior` |
| 6 | Có `comfort_high=4.500.000`, planned 4.000.000, actual 4.300.000 | `on_track` vì dùng comfort_high |
| 7 | Accept advice `adjust_budget` target 2026-11-01 | allocation tháng 11 cập nhật planned 4.500.000; advice `accepted` |
| 8 | Accept advice không gửi `confirm:true` | 422, không đổi budget |

**Golden set AI (`@pytest.mark.ai`)**
| # | Evidence | Automatic checks |
|---|---|---|
| 1 | Food adjust_budget, planned 4.000.000, proposed 4.500.000 | Có observation/explanation/action; nhắc food/Ăn uống; số thuộc evidence |
| 2 | Laptop one_off 6.500.000 | Nhắc laptop và `one_off`; không gợi ý tăng budget |
| 3 | Entertainment adjust_behavior | Không chứa banned phrases, không phán xét |

**Kịch bản thao tác UI**
1. Từ monthly review tháng 10 bấm "Tạo tư vấn điều chỉnh" → chuyển sang `/budget/advice?month=2026-10-01`.
2. Card Food hiển thị evidence 4.4/4.6/4.5 và nút Accept → confirm → budget tháng 11 planned = 4.500.000.
3. Card Shopping hiển thị laptop 6.500.000, chỉ có Dismiss/ghi chú, không có nút Accept tăng budget.
4. Dismiss một advice → card biến khỏi filter `status=open`, vẫn xem được nếu filter `dismissed`.

## 7. Definition of Done

- [ ] Decision tree khớp 100% với `budget-adjustment.md`
- [ ] Tất cả task + verify pass; `pytest` thường không cần API key
- [ ] Accept luôn cần user confirmation và đi qua `budget_service`
- [ ] AI không sinh verdict, không thêm số mới
- [ ] Monthly Review trigger hoạt động
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-08: ...`

## 8. Rủi ro / câu hỏi mở

- CV tính trên actual 3 tháng gần nhất: dùng population std hay sample std; phase này chọn population std để deterministic, ghi rõ trong test.
- Allocation theo `jar_name` có thể gom nhiều category; nếu chưa có mapping jar-category rõ, chỉ generate advice cho allocation có `category_id`, jar để sau.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
