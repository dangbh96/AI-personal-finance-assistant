# Phase 17 — What-if Simulator

| | |
|---|---|
| **ID** | `phase-17-whatif-simulator` |
| **Trạng thái** | Not started |
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

- [ ] T1 Xác định snapshot service đọc baseline income/expense/goals/budget từ DB
- [ ] T2 Implement pure functions `apply_params`, `compute_goal_completion`, `compute_budget_variance`
- [ ] T3 Migration optional `scenarios` + repository nếu quyết định lưu scenario
- [ ] T4 API `/simulator/run` + schemas + validation
- [ ] T5 API save/list/delete scenarios
- [ ] T6 AI narrative structured output + guard validate numbers
- [ ] T7 Coach tool `simulate`
- [ ] T8 Unit tests pure functions với số liệu exact
- [ ] T9 API tests run/save/list/delete
- [ ] T10 UI `/simulator` form + before/after cards + chart/table
- [ ] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-17: what-if simulator`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
cd backend; alembic upgrade head; ruff check .; pytest tests\unit\test_simulator_service.py tests\api\test_simulator.py
cd backend; pytest -m ai tests\ai_golden\test_simulator_narrative.py
cd frontend; npm run gen:api; npm run lint; npm run dev
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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] Pure functions test không cần DB/OpenAI
- [ ] API run không ghi transaction/budget/goal thật
- [ ] Kết quả exact case ăn ngoài/laptop khớp bảng test
- [ ] UI phân biệt rõ "mô phỏng" với "dữ liệu thật"
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-17: what-if simulator`

## 8. Rủi ro / câu hỏi mở

- Quy ước chuyển tháng → ngày: phase này dùng 30 ngày/tháng để test deterministic; nếu UI muốn calendar month thực, cần ghi rõ trong docs.
- Nếu không có budget active, simulator vẫn chạy savings/goal nhưng bỏ qua variance.
- `data-model.md` ghi `SCENARIO` tuỳ chọn; nếu bỏ lưu scenario thì không cần migration, nhưng UI lưu kịch bản sẽ không có.
- Kịch bản nhiều tham số có thể chồng lấn; áp dụng theo thứ tự params và ghi vào result.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
