# Phase 11 — Goals + Pay Yourself First

| | |
|---|---|
| **ID** | `phase-11-goals-pyf` |
| **Trạng thái** | Done |
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

- [x] T1 ORM models + Alembic migration cho `goals`, `goal_contributions`
- [x] T2 Pydantic schemas goal/contribution/proposal + computed fields
- [x] T3 `goal_service` tính remaining, months remaining, suggested monthly saving, on-track status
- [x] T4 `propose_pyf_allocation` nhiều goals theo priority + budget `savings_target`
- [x] T5 Routers `/api/v1/goals/*` + validate income transaction khi allocation
- [x] T6 Mở rộng response `POST /transactions` cho income có `pyf_proposal`
- [x] T7 Unit/API tests cho goal math, priority allocation, duplicate/invalid allocation
- [x] T8 Coach `get_goals` tool registration (nếu registry có sẵn; nếu chưa thì adapter an toàn)
- [x] T9 UI `/goals` goal cards + form + contribution history
- [x] T10 UI dialog "Nhận lương" xác nhận allocation + available spending
- [x] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-11: goals pyf`

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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` xanh không cần API key
- [x] PYF proposal không ghi DB cho tới khi user xác nhận `/goals/allocations`
- [x] Available spending dùng số nguyên VND, không float
- [x] Coach tool `get_goals` read-only nếu Phase 10 đã có registry
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [x] Commit `phase-11: goals pyf`

## 8. Rủi ro / câu hỏi mở

- Cách tính `months_remaining` dễ gây tranh luận ở ranh giới cuối tháng; cần cố định bằng unit test với ngày giả lập.
- `budget.savings_target` có thể trùng goal saving; phase này coi goal allocation là ưu tiên, phần `budget_savings_amount` là khoản tiết kiệm chưa gắn goal và cho user chỉnh về 0 nếu muốn.
- Nếu Phase 10 chưa triển khai trước Phase 11, `get_goals` chỉ chuẩn bị schema/adapter và ghi Handoff để đăng ký sau.
- (Khi triển khai) `on_track` theo đúng định nghĩa plan (`current + suggested × months ≥ target` và chưa quá hạn) gần như luôn đúng trước hạn vì `suggested` làm tròn lên — badge "Chậm tiến độ" thực tế chỉ xuất hiện khi đã quá hạn mà chưa đạt. Chỉ số "theo nhịp" (so với tiến độ tuyến tính / số đã góp tháng này) để Phase 17 (what-if) hoặc sau.
- (Khi triển khai) `suggested_monthly_saving` tính lại từ số hiện có → sau khi đã góp trong tháng, gợi ý cho các tháng còn lại giảm (vd 4.400.000 → 3.600.000) và một thu nhập **thứ hai trong cùng tháng** lại được đề xuất trích tiếp; `budget_savings_amount` cũng được đề xuất lại cho mỗi thu nhập (không lưu nên không biết tháng đã trích bao nhiêu). User chỉnh về 0 được; cần quyết định có lưu "đã trích tháng này" hay không.
- (Khi triển khai) Thu nhập đã xác nhận phân bổ chỉ với `budget_savings_amount` (mọi goal = 0) vẫn hiện trong "Phân bổ từ thu nhập" vì không có bản ghi nào.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22 (bắt đầu 2026-10-21)
- **Đã làm:**
  - **Migration** `20261022_bdb3df82523e_goals_pyf`: `goals` (CHECK `target_amount > 0`, `priority > 0`, `status`; index `(status, priority)`, `(deadline)`) + `goal_contributions` (FK `goal_id` CASCADE, `income_transaction_id` → `transactions` **SET NULL**, CHECK `amount > 0`; index `(goal_id, contributed_on)`, `(income_transaction_id)`). ORM `models/goal.py` (`Goal`, `GoalContribution`), enum `GoalStatus`. Không lưu `current_amount`, không thêm cột vào `transactions`. Chi tiết: [data-model.md § Phase 11](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế).
  - **Deterministic (`services/goal_service`, không AI):** hàm thuần `months_remaining` (tính cả tháng hiện tại, không tính tháng đến hạn, tối thiểu 1 nếu `deadline >= today`, quá hạn → 0), `ceil_to_step` / `suggested_monthly_saving` (làm tròn lên 100.000, không vượt phần còn thiếu; quá hạn → toàn bộ còn thiếu; đạt → 0), `progress_pct`, `compute_progress` (`on_track`, `overdue`), `plan_allocation` (theo priority: min(gợi ý, còn thiếu, thu nhập còn lại) → phần còn lại tối đa `savings_target`). DB: CRUD goal (tự `active ↔ achieved` theo số tiền), khoản góp thủ công + xoá khoản góp, `propose_pyf_allocation` (đề xuất / tính lại số user chỉnh + cảnh báo, không ghi DB), `proposal_for_new_income`, `confirm_allocations` (1 commit, validate trước khi ghi), `list_unallocated_incomes`, `get_goals_overview` (tool Coach). `goal_repository` mới. `transaction_service.update_transaction` chặn đổi thu nhập đã cấp tiền thành khoản chi (409 `income_has_goal_contributions`) / giảm dưới tổng đã phân bổ (422 `amount_below_goal_contributions`).
  - **API** `api/routers/goals.py` (mọi route nhận `?today=`): `GET /goals` (`?status=`, `{items, total_suggested_monthly_saving}`), `POST /goals` (201), `GET/PATCH/DELETE /goals/{id}` (detail = `{goal, contributions}`; DELETE 409 `goal_has_contributions` nếu đã có khoản góp mà chưa tạm dừng), `POST /goals/{id}/contributions` (góp thủ công), `DELETE /goals/{id}/contributions/{cid}`, `GET /goals/unallocated-incomes`, `POST /goals/pyf-proposal`, `POST /goals/allocations` (201). `POST /transactions` trả thêm `pyf_proposal` (thu nhập + có goal active hoặc budget tháng `pyf`; còn lại `null`). Mã lỗi: `goal_not_found` (404 path / 422 trong body), `deadline_in_past`, `target_below_current`, `goal_not_active`, `allocation_exceeds_remaining`, `allocation_exceeds_income`, `duplicate_goal`, `contribution_in_future`, `income_transaction_not_found`, `transaction_not_income` (422), `income_already_allocated` (409), `goal_contribution_not_found` (404). `MAX_AMOUNT` chuyển sang `schemas/common.py` (tránh import vòng `transaction` ↔ `goal`).
  - **Coach:** tool read-only `get_goals` (`finance_tools.goals_tool`, đăng ký trong `default_registry`, output `GetGoalsOutput` = plan § 4.3 + `progress_pct`, `overdue`, `paused_count`, `achieved_count`, `note`); evidence (Số tiền mục tiêu / Đã có / Còn thiếu / Nên để dành / tháng + tổng) và tóm tắt tool trace; `coach_guard.WRITE_OBJECTS` thêm "mục tiêu", "khoản góp" → `/goals`, `LINK_LABELS["/goals"] = "Mục tiêu"`, câu từ chối nhắc "giao dịch, ngân sách hay mục tiêu"; prompt **`coach_v2.md`** (`PROMPT_VERSION = coach_v2`) thêm dòng chọn `get_goals`, ý nghĩa trường goal, link [Mục tiêu](/goals); nhãn tool frontend.
  - **Frontend:** `/goals` (`GoalsPage`, `GoalCard`, `GoalFormDialog`, `ContributionDialog`, `ContributionTimeline`, `PyfAllocationDialog`), hook `usePyfProposal` (debounce gọi `POST /goals/pyf-proposal` khi user chỉnh số), `lib/goals.ts` (nhãn / màu trạng thái), type mới trong `lib/api.ts`, nav "Mục tiêu" bật. Dialog "Nhận lương" mở sau khi tạo thu nhập ở `/transactions` (form) và quick add trang chủ (nhiều thu nhập → lần lượt), và từ nút "Phân bổ" ở `/goals`. `gen:api` chạy lại.
  - **Test:** 709 pass (+55, không cần key): `tests/unit/test_goal_service.py` (ranh giới `months_remaining` 12 trường hợp gồm cuối tháng / qua năm / hôm nay / quá hạn, làm tròn, test case 1–4 thuần), `tests/api/test_goals.py` (test case 1–8 trên DB, CRUD + validate, xoá goal / khoản góp, tự chuyển đã đạt, tính lại số chỉnh + cảnh báo, goal tạm dừng không vào đề xuất, `pyf_proposal` của `POST /transactions` (null khi chưa có goal / budget pyf, có khi budget pyf không có goal, null với khoản chi), thu nhập chưa phân bổ, bảo vệ thu nhập đã phân bổ, xoá thu nhập giữ khoản góp, tool `get_goals` không gọi OpenAI), `tests/api/test_coach.py` (+2: model giả gọi `get_goals` → guard passed + evidence + không tạo khoản góp; "Thêm 2 triệu vào mục tiêu laptop giúp tao" → từ chối kèm link `/goals`).
  - **Golden AI** `tests/ai_golden/test_coach.py`: **7/7 pass** (`gpt-4o-2024-08-06`; mới: "Mục tiêu laptop của tao thế nào, mỗi tháng cần để dành bao nhiêu?" → gọi `get_goals`, trích 4.400.000, guard passed lần đầu; từ chối ghi vào mục tiêu không gọi model). Toàn bộ `pytest -m ai`: **17/17 pass**.
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev, sạch), `ruff check .`, `ruff format --check .`, `pytest` (709), `pytest -m ai` (17), `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh; `npm run start` → `/`, `/goals`, `/goals?today=2026-10-22`, `/transactions`, `/coach`, `/budget` trả 200. Smoke API + UI với **DB tạm `pfa_smoke`** (đã xoá; DB dev chỉ được migrate): budget pyf 10/2026 savings 5.000.000; đủ 6 bước kịch bản UI mục 6 (tạo Laptop 30tr hạn 22/03/2027 + góp 8tr → thẻ "Còn thiếu 22.000.000 ₫ · gợi ý 4.400.000 ₫ / tháng"; thu nhập "Lương tháng 10" 25 triệu ở `/transactions` → dialog đề xuất 4.400.000 + tiết kiệm 5.000.000 → còn 15.600.000; chỉnh 5tr / 3tr → backend tính lại 17.000.000; 23tr → cảnh báo vượt thu nhập + vượt phần còn thiếu, nút xác nhận khoá; xác nhận 4.400.000 → `/goals` 12.400.000 / 30.000.000 (41,3%), lịch sử "Từ thu nhập: Lương tháng 10"; tạm dừng Laptop → thu nhập mới chỉ đề xuất goal còn lại), thêm: nút "Phân bổ" cho thu nhập chưa phân bổ, quick add "Hôm nay nhận lương 25 triệu" (AI thật) → lưu → dialog, "Để sau" → thu nhập xuất hiện ở "Phân bổ từ thu nhập".
- **Lệch so với plan (và lý do):**
  - `months_remaining` cố định: tính cả tháng hiện tại, **không** tính tháng đến hạn (`(năm, tháng)` hạn − hôm nay, tối thiểu 1 nếu chưa quá hạn) — khớp "deadline sau 5 tháng → 5" của test case 1 / kịch bản UI và giải thích vì sao plan cần "tối thiểu 1". `suggested_monthly_saving` không vượt phần còn thiếu; quá hạn → toàn bộ phần còn thiếu (plan chia cho 0).
  - `GET /goals` trả `{items, total_suggested_monthly_saving}` (quy ước danh sách của repo) thay vì mảng trần; `GoalRead` thêm `progress_pct`, `overdue`, `contribution_count`, `last_contributed_on`. PATCH nhận thêm `target_amount` (không nhỏ hơn số đã có). Mọi route goal nhận `?today=` (demo / test như review, advice).
  - Thêm endpoint ngoài bảng plan: góp thủ công `POST /goals/{id}/contributions` (kịch bản UI bước 1 "thêm contribution 8.000.000"), xoá khoản góp (sửa nhầm), `GET /goals/unallocated-incomes` (nút "Phân bổ từ thu nhập" § 4.4).
  - `POST /goals/pyf-proposal` nhận thêm `items` / `budget_savings_amount` để tính lại số user chỉnh (frontend không tự tính tiền) và trả `warnings`, `valid`, `budget_savings_amount`, `goal_total`, `allocated_total`, `income`, `budget_*`. Một thu nhập chỉ xác nhận phân bổ **một lần** (409 `income_already_allocated` cho cả đề xuất và xác nhận) — chống bấm 2 lần / trích trùng.
  - Khoản góp chỉ cho goal `active` và không vượt phần còn thiếu; đủ tiền → tự `achieved` (test case 2), xoá khoản góp / tăng target làm thiếu → `active`. DELETE goal: không có khoản góp **hoặc** đang `paused` (xoá luôn lịch sử góp).
  - `budget_savings_amount` không lưu (plan không có bảng); budget tháng lấy theo tháng của thu nhập, mọi trạng thái. `pyf_proposal` của `POST /transactions` dùng ngày server (request tạo giao dịch không có `today`).
  - FK `income_transaction_id` `ON DELETE SET NULL` (plan chưa nói); thêm chặn sửa thu nhập đã phân bổ ở `transaction_service`.
  - Coach: prompt lên `coach_v2` (thêm `get_goals`), từ chối ghi mở rộng sang "mục tiêu" / "khoản góp".
- **Nợ kỹ thuật / TODO để lại:**
  - Xem mục 8: `on_track` gần như luôn đúng trước hạn; thu nhập thứ hai trong tháng được đề xuất trích lại (goal + tiết kiệm ngân sách); thu nhập phân bổ chỉ cho tiết kiệm ngân sách vẫn hiện "chưa phân bổ".
  - Dòng nhóm `savings` của Budget vs Actual vẫn `not_tracked` (actual 0) — chưa nối với khoản góp goal / `budget_savings_amount`; `insight_service.get_budget_status` chưa đổi.
  - Chưa có `user_id` thực (ADR-004); `priority` cho trùng (hoà → hạn sớm hơn); chưa có UI kéo thả thứ tự ưu tiên.
  - Xoá goal / khoản góp dùng `window.confirm` (đơn giản); chưa có test tự động frontend (Phase 18).
  - Coach chưa trả lời câu hỏi "nếu tăng / giảm tiết kiệm thì đạt mục tiêu khi nào" (what-if — Phase 17).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_goal_service.py tests/api/test_goals.py -q)`
  - `(cd backend && pytest -m ai tests/ai_golden/test_coach.py -s)`
  - `curl -s -X POST "localhost:8000/api/v1/goals?today=2026-10-22" -H "Content-Type: application/json" -d '{"name":"Laptop","target_amount":30000000,"deadline":"2027-03-22","priority":1}'`
  - `curl -s -X POST "localhost:8000/api/v1/goals/pyf-proposal?today=2026-10-22" -H "Content-Type: application/json" -d '{"income_transaction_id":"<id>"}'`
  - `curl -s "localhost:8000/api/v1/goals/unallocated-incomes?today=2026-10-22"`
  - UI: `/goals?today=2026-10-22`.
- **Gợi ý cho phase tiếp theo (Phase 12 — Calendar & cashflow forecast):**
  - `scheduled_goal_savings` = `GoalList.total_suggested_monthly_saving` (hoặc `goal_service.list_goal_status(db, today)` cộng `suggested_monthly_saving`) — đã là số nguyên, chỉ goal `active`. Lưu ý gợi ý giảm sau khi đã góp trong tháng (mục 8); nếu forecast cần "còn phải trích tháng này" thì trừ khoản góp đã có trong tháng (`goal_repository.contribution_totals` / `list_contributions`).
  - Khoản góp goal **không** phải giao dịch chi (không ở `transactions`) — forecast số dư cần quyết định có trừ khoản góp (tiền chuyển sang quỹ riêng) hay không; `available_spending` của PYF chỉ là con số hiển thị, không lưu.
  - Dùng `goal_service.months_remaining` / `compute_progress` (hàm thuần) nếu calendar cần ngày đến hạn / tiến độ.
  - DB dev: đã `alembic upgrade head` (có `goals`, `goal_contributions`, chưa có dữ liệu goal).
