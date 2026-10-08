# Phase 11 — Goals + Pay Yourself First

| | |
|---|---|
| **ID** | `phase-11-goals-pyf` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 4 |
| **Mở khoá** | Phase 12, 17 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 4
2. [glossary.md](../product/glossary.md) — `Goal`, `GoalContribution`, `strategy = "pyf"`
3. [vision.md](../product/vision.md) — Pay Yourself First trong core loop
4. [brainstorm-original.md](../product/brainstorm-original.md#13-goal--pay-yourself-first) — ví dụ 30 triệu, hiện có 8 triệu, còn 5 tháng
5. [core-loop.md](../architecture/core-loop.md) — `INCOME → PAY YOURSELF FIRST → CREATE BUDGET`
6. [data-model.md](../architecture/data-model.md) — `goals`, `goal_contributions`, quan hệ với `transactions`
7. [sequences.md](../architecture/sequences.md#2-nhận-lương--pay-yourself-first--goal-phase-11)
8. [backend-components.md](../architecture/backend-components.md) — `goal_service / pyf`
9. [frontend-structure.md](../architecture/frontend-structure.md) — route `/goals`
10. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: Phase 4 đã Done; có transactions/categories và budget tháng với `strategy`, `expected_income`, `savings_target`; income transaction tạo được qua API Phase 1/2.

## 2. Mục tiêu & giá trị cho user

User tạo mục tiêu tiết kiệm cụ thể, biết mỗi tháng cần để dành bao nhiêu, và khi nhận lương app đề xuất trích tiền cho mục tiêu trước khi tính phần còn lại để chi tiêu. Tính năng này đưa Pay Yourself First vào luồng thật thay vì chỉ là con số savings trong budget.

## 3. Scope

**In scope**
- Bảng `goals`, `goal_contributions` + migration.
- CRUD goals: target amount, deadline, priority, status; current amount tính từ contributions.
- `goal_service` tính `remaining_amount`, `months_remaining`, `suggested_monthly_saving`, `on_track`.
- PYF proposal sau khi tạo income transaction: phân bổ cho nhiều goals theo `priority`, cộng với `budget.savings_target` nếu còn tiền.
- Endpoint `POST /api/v1/goals/allocations` để user xác nhận/chỉnh số; tạo `goal_contributions` gắn `income_transaction_id`.
- `available_spending = income_amount - confirmed_goal_allocations - budget_savings_allocation`.
- UI `/goals`: goal cards, progress, create/edit/pause, contribution history.
- Dialog "Nhận lương" khi income được tạo: hiển thị đề xuất allocation, cho chỉnh trước khi xác nhận.
- Tích hợp Coach tool `get_goals` nếu Phase 10 đã có tool registry.

**Out of scope**
- Tự động chuyển tiền ngân hàng hoặc notification ngoài app.
- What-if simulator thay đổi timeline goal (Phase 17).
- Calendar hiển thị goal saving theo ngày (Phase 12).
- AI tạo goal từ câu tự nhiên; Phase này deterministic CRUD/form.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`goals`: `id UUID PK`, `user_id UUID NULL`, `name TEXT`, `target_amount BIGINT CHECK target_amount > 0`, `deadline DATE`, `priority INT CHECK priority > 0`, `status TEXT CHECK status IN ('active','achieved','paused')`, timestamps.
- Không lưu `current_amount`; tính bằng `COALESCE(SUM(goal_contributions.amount), 0)` để tránh lệch dữ liệu.
- Index `(status, priority)`, `(deadline)`.

`goal_contributions`: `id UUID PK`, `goal_id UUID FK goals(id) ON DELETE CASCADE`, `income_transaction_id UUID FK transactions(id) NULL`, `amount BIGINT CHECK amount > 0`, `contributed_on DATE`, timestamps.
- Validate `income_transaction_id` nếu có phải trỏ tới transaction `direction='income'`.
- Index `(goal_id, contributed_on)`, `(income_transaction_id)`.

Không thêm cột vào `transactions`; relation từ contribution đủ để audit income nào đã cấp tiền cho goal.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/goals` | List goals + computed fields | `?status=active` | `[{id,name,target_amount,current_amount,remaining_amount,months_remaining,suggested_monthly_saving,on_track,priority,status}]` |
| POST | `/api/v1/goals` | Tạo goal | `{name,target_amount,deadline,priority}` | Goal read |
| GET | `/api/v1/goals/{id}` | Chi tiết + contribution history | — | `{goal, contributions:[...]}` |
| PATCH | `/api/v1/goals/{id}` | Sửa name/deadline/priority/status | partial | Goal read |
| DELETE | `/api/v1/goals/{id}` | Xoá goal chưa có contribution hoặc pause | — | `204` hoặc 409 |
| POST | `/api/v1/goals/pyf-proposal` | Tính đề xuất cho income đã tạo | `{income_transaction_id}` | `{income_amount,items,budget_savings_target,available_spending}` |
| POST | `/api/v1/goals/allocations` | User xác nhận allocation | `{income_transaction_id,items:[{goal_id,amount}],budget_savings_amount}` | `{contributions,available_spending}` |

Mở rộng `POST /api/v1/transactions`: nếu transaction mới là `income`, response có thêm `pyf_proposal` khi tồn tại active goals hoặc budget strategy `pyf`; nếu không có thì `pyf_proposal=null`.

`goal_service`:
- `months_remaining(today, deadline)`: số tháng còn lại tính inclusive theo tháng hiện tại, tối thiểu 1 nếu deadline chưa qua; deadline quá hạn nhưng chưa đạt → `0`, `on_track=false`.
- `suggested_monthly_saving = ceil_to_vnd((target_amount - current_amount) / months_remaining, step=100000)`. Ví dụ `(30.000.000 - 8.000.000) / 5 = 4.400.000`.
- `on_track`: current + monthly saving * months remaining đủ đạt target và deadline chưa qua.
- `propose_pyf_allocation(income)`: sort active goals by `priority ASC`, allocate min(suggested, remaining, remaining_income); sau đó allocate budget `savings_target` phần còn lại chưa gắn goal.

### 4.3 AI (nếu có)

Phase 11 không gọi OpenAI. Tất cả phép tính goal/PYF deterministic trong service để test không cần API key. Chuẩn bị tool output cho Coach:

```python
class GoalToolItem(BaseModel):
    goal_id: UUID
    name: str
    target_amount: int
    current_amount: int
    remaining_amount: int
    deadline: date
    months_remaining: int
    suggested_monthly_saving: int
    on_track: bool
    priority: int

class GetGoalsOutput(BaseModel):
    active_goals: list[GoalToolItem]
    total_suggested_monthly_saving: int
```

Nếu Phase 10 đã có `CoachToolRegistry`, đăng ký read-only tool `get_goals()` bọc `goal_service.list_goal_status()`. Tool này chỉ đọc và không tạo contribution.

### 4.4 Frontend

- Route `/goals`:
  - `GoalCard`: tên, progress bar, `current/target`, deadline, badge `on track`/`behind`, suggested monthly saving.
  - `GoalForm`: tạo/sửa goal; amount input hỗ trợ VND integer và shortcut `30tr` nếu helper đã có.
  - `ContributionTimeline`: các khoản góp đã xác nhận.
- Dialog "Nhận lương" sau khi tạo income từ `/transactions` hoặc quick add:
  - Bước 1: transaction income đã lưu.
  - Bước 2: bảng đề xuất: Goal, suggested amount, editable amount, remaining after allocation.
  - Bước 3: dòng `budget_savings_amount` nếu budget tháng có `savings_target`.
  - Bước 4: hiển thị `available_spending`.
- Nếu user đóng dialog chưa xác nhận: income vẫn tồn tại, không tạo contribution; `/goals` có nút "Phân bổ từ thu nhập" cho income chưa dùng.

## 5. Task breakdown

- [ ] T1 ORM models + Alembic migration cho `goals`, `goal_contributions`
- [ ] T2 Pydantic schemas goal/contribution/proposal + computed fields
- [ ] T3 `goal_service` tính remaining, months remaining, suggested monthly saving, on-track status
- [ ] T4 `propose_pyf_allocation` nhiều goals theo priority + budget `savings_target`
- [ ] T5 Routers `/api/v1/goals/*` + validate income transaction khi allocation
- [ ] T6 Mở rộng response `POST /transactions` cho income có `pyf_proposal`
- [ ] T7 Unit/API tests cho goal math, priority allocation, duplicate/invalid allocation
- [ ] T8 Coach `get_goals` tool registration (nếu registry có sẵn; nếu chưa thì adapter an toàn)
- [ ] T9 UI `/goals` goal cards + form + contribution history
- [ ] T10 UI dialog "Nhận lương" xác nhận allocation + available spending
- [ ] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-11: goals pyf`

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
| 1 | Goal target 30.000.000, contributions 8.000.000, deadline còn 5 tháng | `remaining_amount=22000000`, `months_remaining=5`, `suggested_monthly_saving=4400000` |
| 2 | Goal target 10.000.000, current 10.000.000 | `remaining_amount=0`, `suggested_monthly_saving=0`, status đạt hoặc computed achieved |
| 3 | Income 25.000.000; Laptop priority 1 cần 4.400.000; Emergency priority 2 cần 2.000.000; budget savings_target 5.000.000 | Proposal 4.400.000 + 2.000.000 + 5.000.000; `available_spending=13600000` |
| 4 | Income 5.000.000; goal priority 1 cần 4.400.000; budget savings_target 5.000.000 | Goal 4.400.000, budget saving 600.000, `available_spending=0` |
| 5 | POST `/goals/allocations` amount 4.400.000 cho income 25.000.000 | Tạo `goal_contributions`, current goal tăng đúng 4.400.000 |
| 6 | Allocation dùng transaction expense hoặc income không tồn tại | 422 với code rõ ràng |
| 7 | Allocation tổng 26.000.000 cho income 25.000.000 | 422, không tạo partial contributions |
| 8 | `get_goals()` tool sau khi có 2 active goals | Trả tổng suggested monthly saving đúng, không gọi OpenAI |

**Kịch bản thao tác UI**
1. Mở `/goals`, tạo goal "Laptop" target 30.000.000, deadline sau 5 tháng, thêm contribution 8.000.000 nếu UI hỗ trợ.
2. Thấy card hiển thị còn 22.000.000 và gợi ý 4.400.000/tháng.
3. Tạo income "Lương" 25.000.000 từ form transaction.
4. Dialog "Nhận lương" hiện đề xuất 4.400.000 cho Laptop + savings target nếu có; user chỉnh và xác nhận.
5. Quay lại `/goals` thấy progress tăng, contribution history có income transaction.
6. Đặt goal status `paused` → không xuất hiện trong proposal tiếp theo.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` xanh không cần API key
- [ ] PYF proposal không ghi DB cho tới khi user xác nhận `/goals/allocations`
- [ ] Available spending dùng số nguyên VND, không float
- [ ] Coach tool `get_goals` read-only nếu Phase 10 đã có registry
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [ ] Commit `phase-11: goals pyf`

## 8. Rủi ro / câu hỏi mở

- Cách tính `months_remaining` dễ gây tranh luận ở ranh giới cuối tháng; cần cố định bằng unit test với ngày giả lập.
- `budget.savings_target` có thể trùng goal saving; phase này coi goal allocation là ưu tiên, phần `budget_savings_amount` là khoản tiết kiệm chưa gắn goal và cho user chỉnh về 0 nếu muốn.
- Nếu Phase 10 chưa triển khai trước Phase 11, `get_goals` chỉ chuẩn bị schema/adapter và ghi Handoff để đăng ký sau.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
