# Phase 08 — Budget Adjustment Advisor

| | |
|---|---|
| **ID** | `phase-08-budget-advisor` |
| **Trạng thái** | Done |
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

- [x] T1 Migration `budget_advice` + seed `app_settings.budget_advisor`
- [x] T2 Implement `services/advisor_rules.py` đúng decision tree + helper median/CV/rounding
- [x] T3 Query evidence từ budget actual, transactions, history 3 tháng; ưu tiên `comfort_high` nếu có
- [x] T4 AI explanation wrapper + template fallback + guardrail số/banned phrases
- [x] T5 Router `/api/v1/budget/advice*` generate/list/accept/dismiss/settings
- [x] T6 Unit tests 4 standard cases từ `budget-adjustment.md`
- [x] T7 API tests accept/dismiss + user confirmation required
- [x] T8 Frontend `/budget/advice` + monthly review trigger
- [x] T9 Golden AI tests `@pytest.mark.ai` cho explanation trung lập
- [x] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-08: budget advisor`

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

- [x] Decision tree khớp 100% với `budget-adjustment.md`
- [x] Tất cả task + verify pass; `pytest` thường không cần API key
- [x] Accept luôn cần user confirmation và đi qua `budget_service`
- [x] AI không sinh verdict, không thêm số mới
- [x] Monthly Review trigger hoạt động
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [x] Commit `phase-08: ...`

## 8. Rủi ro / câu hỏi mở

- CV tính trên actual 3 tháng gần nhất: dùng population std hay sample std; phase này chọn population std để deterministic, ghi rõ trong test.
  - **Đã chốt:** population std (chia n); quyết định so `CV² ≤ ngưỡng²` trên `Fraction` (không sai số float). Test `test_cv_exactly_at_threshold_is_stable`.
- Allocation theo `jar_name` có thể gom nhiều category; nếu chưa có mapping jar-category rõ, chỉ generate advice cho allocation có `category_id`, jar để sau.
  - **Đã chốt:** mapping đã rõ từ Phase 4 (`budget_service.allocation_scope`: hũ → danh mục, dòng nhóm → spending_type) nên advice tạo cho mọi dòng **trừ nhóm `savings`**. Lưu ý: dòng nhóm `irregular` (50/30/20, PYF) khớp toàn giao dịch bất thường nên khi vượt luôn ra `one_off`.
- Bước 2 decision tree "có giao dịch `irregular` hoặc 1 giao dịch đơn lẻ chiếm ≥ 60% phần vượt" được hiểu là **tổng giao dịch `irregular`** ≥ 60% phần vượt **hoặc** giao dịch lớn nhất ≥ 60% phần vượt (một khoản bất thường 50.000 trong dòng vượt 2.000.000 không làm cả dòng thành `one_off`).
- "Lịch sử" = `min_history_months` tháng gần nhất **tính cả tháng đang xét**; một tháng được tính là có dữ liệu khi có ≥ 1 giao dịch chi trong phạm vi dòng. "Đều vượt planned" so với planned của tháng đang xét.
- Planned đề xuất có thể ≤ planned hiện tại nếu planned không phải bội số của bước làm tròn (vd planned 4.020.000, median 4.040.000 → 4.000.000). Chưa xử lý — hiếm gặp; Phase sau có thể làm tròn lên khi kết quả ≤ planned.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:** 2026-10-21
- **Đã làm:**
  - **Migration** `20261021_461f51a98cbc_budget_advice`: bảng `budget_advice` (CHECK `verdict`, `status`, `month` ngày 1; FK `budget_allocation_id` `ON DELETE CASCADE`; **unique một phần** `(budget_allocation_id, month) WHERE status = 'open'`; index `month`, `budget_allocation_id`) + cột thêm `narrative JSONB`, `model`, `applied_month`, `dismiss_reason`. Seed `app_settings.budget_advisor` (0.6 / 0.15 / 3 / 100000), downgrade xoá key. ORM `models/budget_advice.py`, enum `AdviceVerdict` / `AdviceStatus`.
  - **Deterministic (services):**
    - `advisor_rules`: `evaluate(AdviceInput, Thresholds)` → `verdict` + `BudgetAdviceEvidence` (planned/actual/variance, `comfort_high` + `threshold_amount`/`over_amount`, giao dịch lớn nhất + share, tổng/tỉ lệ bất thường, `one_off_transaction`, `history_actuals` (3 tháng tính cả tháng xét), `history_months`, `all_over_planned`, `cv`/`cv_pct` (population), `history_median`, `proposed_planned_amount`, ngưỡng dạng %, `rule`). Helper `median`, `cv_squared` (Fraction), `round_proposed`.
    - `advice_narrative`: `allowed_numbers` / `prompt_numbers` (evidence bỏ ID), `validate_explanation` (3 tầng, action có điều kiện trừ `on_track`, số ⊆ evidence, cụm phán xét + "tôi đã điều chỉnh…/app đã…", verdict ≠ `adjust_budget` cấm gợi ý tăng ngân sách, `adjust_budget` phải nêu planned đề xuất, `one_off` phải nêu giao dịch ngoại lệ, cấm lộ tên trường kỹ thuật kiểu `cv_pct`), `template_explanation` (luôn qua validate), `join_text`.
    - `budget_advice_service`: `get_settings` / `update_settings` (key thiếu/sai → mặc định), `compute_evidence` (budget active/closed, scope dòng qua `analytics_service.scope_resolver`, aggregate 3 tháng + giao dịch trong phạm vi `transaction_repository.all_in_scope`, `comfort_high` đọc bằng `getattr` để Phase 9 tự áp dụng), `prepare_advice` / `save_advice`, `accept_advice`, `dismiss_advice`, `to_read`.
    - `budget_service`: `ensure_next_month_budget` (chưa có → nháp copy từ tháng của advice, chỉ flush), `set_allocation_planned` (sửa **tại chỗ** dòng cùng danh mục/hũ — giữ id; thiếu dòng → thêm cuối; cùng validate chồng lấn / vượt thu nhập; budget đóng → 409). `copy_from_previous_month` tách `_copy_budget` (không commit). `analytics_service.tracked_budget` / `scope_resolver`; `review_narrative.contains_phrase` / `has_conditional` / `collect_numbers` (public).
  - **AI:** `ai/advice_writer.py` + prompt `budget_advice_explanation.v1.md` (verdict + hướng dẫn theo verdict + evidence JSON + số được phép), `OPENAI_MODEL_FAST`, timeout 30s, validate qua `structured_completion(validate=…)` (sai → model sửa 1 lần) → vẫn sai / AI lỗi → template (`model = fallback_template`, `narrative.fallback_reason` = mã lỗi). `on_track` dùng template (`model = template`, không gọi AI). Nhiều dòng → gọi song song (`MAX_PARALLEL = 4`).
  - **API** `api/routers/budget_advice.py` (`/api/v1/budget/advice`): `GET ?month&status&allocation_id`, `POST /generate {month, allocation_id, regenerate, today}` (trả mọi advice của tháng), `POST /{id}/accept {confirm, target_month, confirm_over_income}` → `{advice, updated_allocation, budget{id, period_month, status, created}}`, `POST /{id}/dismiss {reason}`, `GET`/`PATCH /settings`. Mã lỗi: `confirmation_required`, `advice_not_adjustable`, `invalid_target_month` (422); `advice_not_open`, `budget_closed` (409); `advice_not_found`, `allocation_not_found`, `budget_not_found`, `budget_not_active` (404); `allocation_not_tracked`, `month_not_started`, `planned_exceeds_income` (422).
  - **Frontend:** `/budget/advice` thay trang giữ chỗ — `BudgetAdvicePage` (tháng `?month=YYYY-MM-01`, mặc định tháng trước; lọc `?status=open|accepted|dismissed|all` kèm số đếm; "Tạo tư vấn điều chỉnh" / "Tính lại tư vấn đang chờ"; lỗi chưa có ngân sách → link `/budget`), `BudgetAdviceList`, `AdviceCard` (badge verdict, 3 tầng + nguồn AI/tự động, trạng thái), `EvidenceTable` (planned/actual/vượt, giao dịch ngoại lệ, bảng 3 tháng, trung vị, CV, planned đề xuất), `AcceptAdviceDialog` (chỉ `adjust_budget` đang open; xác nhận → `confirm: true`; `planned_exceeds_income` → tick thêm xác nhận), `DismissButton` (ghi chú tuỳ chọn), `AdvisorSettingsPanel` (`<details>`). `MonthlyReviewPage`: CTA "Tạo tư vấn điều chỉnh" gọi generate rồi `router.push('/budget/advice?month=…')` (+ "Xem tư vấn đã có"). `lib/advice.ts` (nhãn verdict). `gen:api` chạy lại.
  - **Test:** 547 pass (+56): `tests/unit/test_advisor_rules.py` (36 — test case 1–6, biên 60% / CV 15% đúng ngưỡng, nhiều khoản bất thường cộng lại, làm tròn half-up, thresholds từ settings, median/CV, template luôn hợp lệ, validate số bịa / phán xét / thiếu planned đề xuất / gợi ý tăng budget khi `one_off` / tên trường kỹ thuật), `tests/api/test_budget_advice.py` (20 — generate 4 case chuẩn không AI, AI giả + prompt không chứa ID, retry rồi fallback, giữ advice open / regenerate, lỗi tháng/dòng/budget nháp, case 5 thiếu lịch sử, list/filter, accept tạo nháp tháng 11 (test 7), accept sửa tại chỗ / thêm dòng thiếu, thiếu confirm → 422 không đổi budget (test 8), sai verdict / đã xử lý / tháng đích, vượt thu nhập cần xác nhận thêm, budget đóng → 409, dismiss + không tạo lại, settings + áp dụng ngưỡng mới, xoá budget nháp xoá advice). Dữ liệu `tests/advice_dataset.py`.
  - **Golden AI** `tests/ai_golden/test_budget_advice_explanation.py`: **4/4 pass** với `gpt-4o-mini` (3 golden plan + 1 chống prompt phán xét); lần gọi đầu đều qua validate (~3–6s/advice).
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check`, `ruff check .`, `ruff format --check .`, `pytest` (547), `pytest tests/unit/test_advisor_rules.py tests/api/test_budget_advice.py`, `pytest -m ai tests/ai_golden/test_budget_advice_explanation.py`, `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm run dev` (các trang trả 200) xanh. Kịch bản UI mục 6 chạy trên trình duyệt (bản build `npm run start`) với **DB tạm `pfa_smoke`** seed `tests/advice_dataset` (đã xoá sau khi chạy — DB dev không bị ghi advice): review tháng 10 (gpt-4o) → "Tạo tư vấn điều chỉnh" → `/budget/advice?month=2026-10-01` với 4 thẻ (Ăn uống 4.4/4.6/4.5 + nút Áp dụng; Mua sắm Laptop 6.500.000 chỉ có Bỏ qua; Giải trí; Đi lại) → Áp dụng → xác nhận → ngân sách 11/2026 (nháp) Ăn uống 4.500.000 → Bỏ qua Mua sắm kèm ghi chú → biến khỏi "Chờ quyết định", hiện ở "Đã bỏ qua"; lưu ngưỡng ở panel.
- **Lệch so với plan (và lý do):**
  - Bảng `budget_advice` thêm `narrative` (3 tầng + `generated_by` + `fallback_reason`), `model`, `applied_month`, `dismiss_reason`; `explanation` = 3 tầng nối thành 1 đoạn — UI hiển thị theo tầng, biết nguồn AI/template, tháng đã áp dụng và lý do bỏ qua.
  - Evidence thêm `variance`, `threshold_amount`, `largest_transaction`, `irregular_total`/`irregular_share`, `one_off_transaction`, `history_months`, `all_over_planned`, `history_median`, các trường `*_pct`, ngưỡng, `rule`, `as_of`/`month_complete` — để template/AI trích số có sẵn (không tự tính) và UI giải thích nhánh. `irregular_transaction` = khoản bất thường lớn nhất; giao dịch được "chỉ ra" khi `one_off` là `one_off_transaction`.
  - Bước 2 hiểu là tổng giao dịch bất thường **hoặc** 1 giao dịch đơn lẻ ≥ 60% phần vượt (xem mục 8). Lịch sử tính cả tháng đang xét.
  - Generate request thêm `regenerate`, `today`; generate yêu cầu budget active/closed (nháp → 404 `budget_not_active`), bỏ qua dòng `savings`; advice đã accepted/dismissed không tạo lại. Accept thêm `confirm_over_income` (tái dùng quy tắc Phase 4), response thêm `budget`; `target_month` mặc định tháng sau, phải sau tháng của advice. Accept sửa dòng **tại chỗ** (không thay toàn bộ phân bổ như PATCH budget) để không làm mất id dòng / advice của tháng đích.
  - Verdict `on_track` dùng template, không gọi AI (tiết kiệm token, nội dung cố định). Thêm guardrail cấm lộ tên trường kỹ thuật sau khi golden lần đầu thấy model viết "(cv_pct)".
  - Không thêm route `/budget/advice` vào nav (đến từ review tháng / link ở trang); thêm link "Review tháng" / "Ngân sách tháng" trên trang.
- **Nợ kỹ thuật / TODO để lại:**
  - FK `ON DELETE CASCADE`: PATCH budget với `allocations` (Phase 4) **thay toàn bộ dòng** → advice của tháng đó bị xoá theo. Nên giữ id dòng khi PATCH (khớp theo danh mục/hũ) nếu advice cần bền hơn.
  - Planned đề xuất có thể ≤ planned hiện tại trong trường hợp làm tròn hiếm (mục 8). Chưa có "hoàn tác" accept (user sửa tay ở `/budget`).
  - Advice `open` không tự cập nhật khi giao dịch đổi — cần bấm "Tính lại". Advice tháng đang chạy dùng số liệu tới hôm nay (`month_complete = false`).
  - Allowed numbers vẫn là tập giá trị (không theo ngữ cảnh), như Phase 6/7. `budget_advice` UNIQUE một phần chưa có `user_id`. Không có test tự động frontend (Phase 18).
  - DB dev: đã `alembic upgrade head` (có bảng `budget_advice` + settings), **chưa** tạo advice nào. Dữ liệu dev tháng 8–10 không khớp 4 case chuẩn (Ăn uống 4.931.000 / 3.569.000 / 4.500.000 → `adjust_behavior`; Mua sắm tai nghe 900.000 = 75% phần vượt → `one_off`).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_advisor_rules.py tests/api/test_budget_advice.py -q)`
  - `(cd backend && pytest -m ai tests/ai_golden/test_budget_advice_explanation.py -s)`
  - `curl -s -X POST localhost:8000/api/v1/budget/advice/generate -H "Content-Type: application/json" -d '{"month":"2026-10-01","today":"2026-11-02"}'`
  - `curl -s -X POST localhost:8000/api/v1/budget/advice/<id>/accept -H "Content-Type: application/json" -d '{"confirm":true,"target_month":"2026-11-01"}'`
  - UI: `/reviews/monthly/2026-10?today=2026-11-02` → "Tạo tư vấn điều chỉnh"; `/budget/advice?month=2026-10-01&status=all`.
- **Gợi ý cho phase tiếp theo (Phase 9 — Flexible budget zones):**
  - Thêm cột `comfort_high` trên `budget_allocations` là đủ để advisor dùng: `budget_advice_service.compute_evidence` đọc `getattr(allocation, "comfort_high", None)` → `advisor_rules` so `actual` với `comfort_high` (test case 6 đã có ở mức hàm thuần). Nên thêm test API khi cột tồn tại; nếu auto mode chỉ tính khi đọc (không cache cột), truyền giá trị đã tính vào `AdviceInput.comfort_high` thay vì `getattr`.
  - `budget_service._copy_budget` / `_set_allocations` / `set_allocation_planned` hiện chỉ copy/ghi `group`, `category_id`, `jar_name`, `planned_amount`, `position` — cần copy thêm cột zone (manual) hoặc tính lại zone sau khi planned đổi (accept advice).
  - `EvidenceTable` đã hiển thị "Vùng an toàn (tới)" / "Vượt vùng an toàn" khi `comfort_high_used = true`.
