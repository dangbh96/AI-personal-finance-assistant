# Phase 17 — What-if Simulator

| | |
|---|---|
| **ID** | `phase-17-whatif-simulator` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 11 phải Done |
| **Mở khoá** | Phase 18 |
| **Milestone** | — (stretch) |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 11
2. [vision.md](../product/vision.md) — AI không quyết định thay user, chỉ diễn giải
3. [glossary.md](../product/glossary.md) — `Scenario`, `Goal`, Pay Yourself First
4. [data-model.md](../architecture/data-model.md) — optional `SCENARIO`
5. [backend-components.md](../architecture/backend-components.md) — `services/simulator_service`
6. [frontend-structure.md](../architecture/frontend-structure.md) — route `/simulator`
7. [ai-architecture.md](../architecture/ai-architecture.md) — Coach tool `simulate`
8. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: Phase 11 đã có goals, goal contributions, Pay Yourself First proposal và analytics đủ để lấy baseline monthly savings.

## 2. Mục tiêu & giá trị cho user

User thử kịch bản giả định như "giảm ăn ngoài 20%", "tăng thu nhập 2 triệu", "thêm subscription 199k/tháng", "đổi deadline goal" để thấy tác động tới monthly savings, ngày hoàn thành goal và budget variance — không ghi đè dữ liệu thật.

## 3. Scope

**In scope**
- `simulator_service` là pure functions, nhận params + baseline snapshot, trả result; không ghi transaction/budget/goal thật.
- Các scenario: reduce category by %, change income, add new recurring expense, change goal deadline.
- Optional bảng `scenarios` để lưu kịch bản user đặt tên.
- API run/save/list/delete scenario.
- Coach tool `simulate`.
- AI diễn giải kết quả bằng `OPENAI_MODEL_FAST` structured narrative.
- UI `/simulator` với form kịch bản và biểu đồ before/after.

**Out of scope**
- Tối ưu tự động "nên giảm khoản nào" (Phase 8/10 đã tư vấn).
- Monte Carlo/uncertainty simulation.
- Ghi trực tiếp budget mới từ simulator.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Tuỳ chọn nếu lưu kịch bản:
`scenarios`: `id`, `user_id NULL`, `name`, `params JSONB`, `result JSONB`, `created_at`, `updated_at`.

Không thay đổi `transactions`, `budgets`, `goals`. Mọi input tài chính tính từ snapshot read-only:
- baseline income/month
- expense by category/month
- current budget allocations/variance
- active goals: remaining amount, current monthly contribution, deadline

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| POST | `/api/v1/simulator/run` | Chạy kịch bản không lưu | `SimulationRequest` | `SimulationResult` |
| POST | `/api/v1/simulator/scenarios` | Lưu kịch bản + result hiện tại | `{name, params}` | Scenario |
| GET | `/api/v1/simulator/scenarios` | Danh sách scenario đã lưu | — | `Scenario[]` |
| DELETE | `/api/v1/simulator/scenarios/{id}` | Xoá scenario | — | 204 |

Pydantic schemas:
```python
class ReduceCategoryParam(BaseModel):
    type: Literal["reduce_category"]
    category_id: UUID
    percent: conint(gt=0, le=100)

class ChangeIncomeParam(BaseModel):
    type: Literal["change_income"]
    delta_amount: int

class AddRecurringExpenseParam(BaseModel):
    type: Literal["add_recurring_expense"]
    name: str
    amount: int
    category_id: UUID

class ChangeGoalDeadlineParam(BaseModel):
    type: Literal["change_goal_deadline"]
    goal_id: UUID
    new_deadline: date

class SimulationResult(BaseModel):
    baseline_monthly_savings: int
    projected_monthly_savings: int
    delta_monthly_savings: int
    goal_impacts: list[GoalImpact]
    budget_variance_after: list[BudgetVarianceImpact]
    narrative: str | None = None
```

Core pure functions:
- `apply_params(snapshot, params) -> ProjectedSnapshot`
- `compute_goal_completion(remaining_amount, monthly_savings) -> months, days, date`
- `compute_budget_variance(projected_expense_by_category, allocations)`

### 4.3 AI

- Model: `OPENAI_MODEL_FAST` (ví dụ `gpt-4o-mini`) cho narrative có cấu trúc; `OPENAI_MODEL_SMART` không cần.
- Prompt outline: nhận `SimulationResult` deterministic, viết 3 phần Observation → Explanation → Action; không tự tính lại số; nếu kịch bản làm savings âm thì cảnh báo trung lập.
- Structured output:
```python
class SimulationNarrative(BaseModel):
    observation: str
    explanation: str
    action: str | None
    caveats: list[str]
```
- Guardrails: AI không được ghi DB, không đề xuất vay/đầu tư rủi ro; mọi số trong narrative phải nằm trong result; câu chữ "có thể cân nhắc", không "phải".

Coach tool `simulate(params)` gọi cùng service, trả result ngắn + link `/simulator`.

### 4.4 Frontend

- Route `/simulator`.
- `ScenarioForm`: chọn goal, category, percent/income/expense/deadline; validate percent 1–100.
- `BeforeAfterCards`: monthly savings baseline/projected/delta.
- `GoalImpactChart`: timeline before/after theo ngày hoàn thành.
- `BudgetVarianceTable`: planned/actual/projected variance theo category.
- Nút "Lưu kịch bản" tuỳ chọn, không có nút "Áp dụng vào dữ liệu thật" trong phase này.

## 5. Task breakdown

- [x] T1 Xác định snapshot service đọc baseline income/expense/goals/budget từ DB
- [x] T2 Implement pure functions `apply_params`, `compute_goal_completion`, `compute_budget_variance`
- [x] T3 Migration optional `scenarios` + repository nếu quyết định lưu scenario
- [x] T4 API `/simulator/run` + schemas + validation
- [x] T5 API save/list/delete scenarios
- [x] T6 AI narrative structured output + guard validate numbers
- [x] T7 Coach tool `simulate`
- [x] T8 Unit tests pure functions với số liệu exact
- [x] T9 API tests run/save/list/delete
- [x] T10 UI `/simulator` form + before/after cards + chart/table
- [x] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-17: what-if simulator`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
(cd backend && alembic upgrade head && ruff check . && pytest tests/unit/test_simulator_service.py tests/api/test_simulator.py)
(cd backend && pytest -m ai tests/ai_golden/test_simulator_narrative.py)
(cd frontend && npm run gen:api && npm run lint && npm run dev)
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Base eating-out 1.500.000/tháng, giảm 20% | `delta_monthly_savings = 300000` |
| 2 | Laptop goal còn 22.000.000, baseline saving 4.400.000/tháng | Hoàn thành sau 5,0 tháng = 150 ngày |
| 3 | Sau giảm ăn ngoài, saving 4.700.000/tháng | Hoàn thành sau ≈ 4,68 tháng = 141 ngày (làm tròn lên), sớm hơn 9 ngày |
| 4 | Start date 2026-10-07 | Before `2027-03-06`, after `2027-02-25` |
| 5 | Add recurring expense 199.000/tháng | `projected_monthly_savings` giảm 199.000 |
| 6 | Change income `+2.000.000` | `projected_monthly_savings` tăng 2.000.000 nếu expense không đổi |
| 7 | Percent 0 hoặc 150 | 422 validation |
| 8 | AI narrative | Có số 300.000 và 9 ngày; không chứa "bạn phải" |

**Kịch bản thao tác UI**
1. Mở `/simulator`, chọn category Ăn ngoài/Ăn uống, nhập giảm 20%, chọn goal Laptop.
2. Nhấn "Chạy mô phỏng" → thấy savings +300.000/tháng, goal sớm hơn 9 ngày.
3. Thêm scenario "Tăng thu nhập 2 triệu" → cards/chart cập nhật.
4. Lưu kịch bản "Giảm ăn ngoài 20%" → reload vẫn thấy trong danh sách.
5. Hỏi Coach "Nếu giảm ăn ngoài 20% thì sao?" → Coach gọi tool `simulate` và link sang `/simulator`.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] Pure functions test không cần DB/OpenAI
- [x] API run không ghi transaction/budget/goal thật
- [x] Kết quả exact case ăn ngoài/laptop khớp bảng test
- [x] UI phân biệt rõ "mô phỏng" với "dữ liệu thật"
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [x] Commit `phase-17: what-if simulator`

## 8. Rủi ro / câu hỏi mở

- Quy ước chuyển tháng → ngày: phase này dùng 30 ngày/tháng để test deterministic; nếu UI muốn calendar month thực, cần ghi rõ trong docs.
- Nếu không có budget active, simulator vẫn chạy savings/goal nhưng bỏ qua variance.
- `data-model.md` ghi `SCENARIO` tuỳ chọn; nếu bỏ lưu scenario thì không cần migration, nhưng UI lưu kịch bản sẽ không có.
- Kịch bản nhiều tham số có thể chồng lấn; áp dụng theo thứ tự params và ghi vào result.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22
- **Đã làm:**
  - **Migration** `20261022_36ad973fa6c3_whatif_simulator`: bảng `scenarios` (`name`, `params JSONB`, `result JSONB`, index `created_at`). ORM `models/scenario.py`, `repositories/scenario_repository.py`.
  - **Deterministic** `services/simulator_service`: `build_snapshot` (chỉ đọc: trung bình / tháng của N tháng trọn gần nhất trước tháng `start_date` — thu nhập, chi theo (danh mục, loại chi tiêu), mặc định bỏ `irregular`; mục tiêu active còn thiếu / hạn / priority; ngân sách active / closed của tháng `start_date` → dòng + phạm vi theo `budget_service.allocation_scope`, bỏ nhóm savings); hàm thuần `apply_params` (áp theo thứ tự; giảm % làm tròn `round_vnd`; thu nhập không âm), `compute_goal_completion` (tháng 2 chữ số, ngày = ⌈còn thiếu × 30 / tiết kiệm⌉), `goal_impacts` (dồn tiết kiệm theo priority, ngày đạt, sớm hơn, cần / tháng để kịp hạn theo công thức Phase 11, kịp hạn), `compute_budget_variance`, `category_changes`, `simulate`; validate tham số (danh mục chi tồn tại, mục tiêu active, hạn mới sau ngày bắt đầu, thu nhập ≠ 0); lưu / liệt kê / xoá kịch bản; `simulate_for_coach`. `services/simulator_narrative` (số được phép gồm phần ngày ISO + 30, cụm cấm + không gợi ý vay / đầu tư (so khớp có dấu), action có điều kiện, `template_narrative`).
  - **AI** `ai/simulator_writer` + prompt `simulator_narrative.v1.md` (`OPENAI_MODEL_FAST`, structured output `SimulationNarrative`, validate → sửa 1 lần → bản mẫu; không 503).
  - **API** `POST /simulator/run?today=` (`SimulationRequest`: `params[]` union theo `type`, `baseline_months` 1–12, `include_irregular`, `start_date?`, `with_narrative`), `GET/POST /simulator/scenarios`, `DELETE /simulator/scenarios/{id}`.
  - **Coach** tool thứ 9 `simulate` (slug danh mục, % giảm, thu nhập ±, khoản chi định kỳ mới) + evidence / tóm tắt, prompt `coach_v5.md`.
  - **Frontend** `/simulator` (banner mô phỏng, form nhiều thay đổi, thẻ trước / sau, diễn giải, biểu đồ số ngày đạt mục tiêu (Recharts), bảng mục tiêu / ngân sách / danh mục, lưu / mở / xoá kịch bản), nav "Mô phỏng", nhãn tool Coach.
  - **Test:** **1166 pass** (+36): `tests/unit/test_simulator_service.py` (test case 1–7 với số chính xác: +300.000; 150 → 141 ngày, 06/03/2027 → 25/02/2027, sớm hơn 9 ngày; −199.000; +2.000.000; percent 0 / 150 → lỗi; thứ tự tham số; thu nhập âm; mục tiêu theo priority; đổi hạn; budget variance; cảnh báo; bản mẫu có "300.000" + "9 ngày" và qua validate; validate bắt số bịa / "bạn phải" / "vay"; "vậy" không bị nhầm), `tests/api/test_simulator.py` (dữ liệu DB thật: số chính xác + **không ghi** giao dịch / ngân sách / mục tiêu / khoản góp; thu nhập + khoản định kỳ; bất thường / số tháng nền; 422 các loại; đổi hạn; ngân sách tháng; DB rỗng; diễn giải AI giả / sai 2 lần → mẫu / thiếu key → mẫu; tool Coach + evidence; Coach end-to-end với model giả; CRUD kịch bản).
  - **Golden (`pytest -m ai`, gpt-4o-mini + gpt-4o, 2026-10-22):** `tests/ai_golden/test_simulator_narrative.py` **3/3** — diễn giải giảm Ăn uống 20% do AI viết có "300.000" và "9 ngày"; thêm Netflix 199.000 qua validate; Coach "Nếu tao giảm ăn ngoài 20% thì sao?" gọi `simulate`, trích 300.000, link `/simulator`, guard passed.
- **Lệch so với plan (và lý do):**
  - Mức nền mặc định bỏ khoản `irregular` (tham số `include_irregular`), N tháng trọn gần nhất (mặc định 3) — plan không nói baseline tính thế nào; khoản một lần làm sai mức tiết kiệm hằng tháng.
  - Nhiều mục tiêu: tiết kiệm / tháng dồn theo priority (mục tiêu sau đạt khi đủ tổng phần còn thiếu của các mục tiêu trước) — plan chỉ nêu ví dụ 1 mục tiêu.
  - Đổi hạn mục tiêu không đổi ngày đạt (ngày đạt chỉ phụ thuộc tiết kiệm), mà đổi "cần để dành / tháng" và "kịp hạn".
  - Response thêm `baseline_from/to`, `baseline_monthly_income/expense`, `projected_*`, `applied[]` (đóng góp từng thay đổi), `category_changes`, `budget_month`, `warnings`, `narrative_source/model`; `GoalImpact` / `BudgetVarianceImpact` chi tiết hơn plan. Schema đổi tên `SimulationCategoryChange` (trùng `CategoryChange` của review).
  - Tool Coach `simulate` nhận slug + tham số phẳng (model không biết UUID) và chỉ hỗ trợ 3 loại thay đổi (không đổi hạn mục tiêu).
  - Narrative chỉ tạo khi `with_narrative=true`; kịch bản lưu không kèm narrative.
- **Nợ kỹ thuật / TODO để lại:**
  - Quy ước 30 ngày / tháng (theo plan); chưa mô phỏng theo lịch thật / theo khoản định kỳ Phase 12.
  - Khoản định kỳ mới chỉ theo tháng; chưa có kịch bản "giảm theo số tiền", "chi một lần".
  - Kịch bản lưu là ảnh chụp kết quả lúc lưu (mở lại sẽ chạy lại với số liệu mới).
  - Dev: trình duyệt nhúng của công cụ treo Suspense khi tab ở nền (không ảnh hưởng người dùng thật).
- **Lệnh hữu ích:**
  ```bash
  (cd backend && pytest tests/unit/test_simulator_service.py tests/api/test_simulator.py)
  (cd backend && pytest -m ai -s tests/ai_golden/test_simulator_narrative.py)
  curl -X POST "http://localhost:8000/api/v1/simulator/run?today=2026-10-07" -H "Content-Type: application/json" \
    -d '{"params":[{"type":"change_income","delta_amount":2000000}],"with_narrative":true}'
  ```
- **Gợi ý cho phase tiếp theo:** Phase 18 gom AI usage: `structured_completion` / `chat_with_tools` / `create_embeddings` đều log `ai task=… model=… tokens`, có thể ghi thêm vào bảng `ai_call_logs`; guard regression từ khoá cấm đã có cho review / coach / simulator (`coach_guard.BANNED_PHRASES`).
