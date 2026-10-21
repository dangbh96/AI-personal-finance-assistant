# Progress

> Cập nhật file này **mỗi khi bắt đầu và kết thúc một phase** (hoặc khi dừng giữa chừng).
> Trạng thái: `Not started` · `In progress` · `Done` · `Blocked`

## Phase hiện tại

**Tiếp theo: [Phase 12 — Calendar & cashflow forecast](./phases/phase-12-calendar-forecast.md)** · **M5 (AI Agent) đã đạt** sau Phase 10 · M4 (MVP) đạt sau Phase 7

Handoff Phase 11: xem [phase-11-goals-pyf.md § 9](./phases/phase-11-goals-pyf.md#9-handoff-notes). Bảng `goals` (priority, status `active | achieved | paused`, **không** lưu `current_amount`) + `goal_contributions` (`income_transaction_id` NULL = góp thủ công, FK SET NULL khi xoá thu nhập). `services/goal_service` (deterministic, không AI): `months_remaining` tính cả tháng hiện tại, không tính tháng đến hạn (tối thiểu 1, quá hạn 0); `suggested_monthly_saving` làm tròn lên 100.000; đề xuất PYF theo priority → `savings_target` của budget tháng thu nhập → `available_spending`; chỉ `POST /goals/allocations` ghi khoản góp (1 thu nhập xác nhận 1 lần). API `/api/v1/goals…` (`?today=`), `POST /transactions` trả `pyf_proposal` cho thu nhập. UI `/goals` + dialog "Nhận lương" (`/transactions`, quick add, nút "Phân bổ từ thu nhập"). Coach có tool read-only `get_goals` (prompt `coach_v2.md`). Phase 12: tổng gợi ý / tháng của goal active = `GoalList.total_suggested_monthly_saving` (hoặc `goal_service.list_goal_status`); khoản góp không phải giao dịch chi; gợi ý giảm sau khi đã góp trong tháng (xem § 8 Phase 11). Postgres vẫn ở **port 5433**.

## Bảng trạng thái

| Phase | Tên | Trạng thái | Bắt đầu | Hoàn thành | Milestone | Ghi chú |
|---|---|---|---|---|---|---|
| D | [System design & plan export](./phases/phase-D-design-docs.md) | Done | 2026-10-07 | 2026-10-07 | | Tài liệu thiết kế + plan 20 phase |
| 0 | [Scaffolding](./phases/phase-00-scaffolding.md) | Done | 2026-10-08 | 2026-10-08 | | Next.js 16.4, shadcn base-nova, DB port 5433 |
| 1 | [Core transactions](./phases/phase-01-transactions.md) | Done | 2026-10-08 | 2026-10-08 | M1 ✅ | 93 test; summary nhận thêm filter |
| 2 | [AI natural language entry](./phases/phase-02-nl-entry.md) | Done | 2026-10-13 | 2026-10-15 | | 171 test (mock); golden 12 câu đạt 100% (prompt v2) |
| 3 | [Classification learning](./phases/phase-03-classification-learning.md) | Done | 2026-10-19 | 2026-10-19 | M2 ✅ | 259 test (mock); golden 10 bước đạt 100% |
| 4 | [Budget engine](./phases/phase-04-budget-engine.md) | Done | 2026-10-19 | 2026-10-19 | | 333 test; dòng nhóm khớp theo spending_type |
| 5 | [Budget vs Actual](./phases/phase-05-budget-vs-actual.md) | Done | 2026-10-20 | 2026-10-20 | M3 ✅ | 369 test; thêm `not_tracked` (savings), `unbudgeted_actual` |
| 6 | [Weekly review](./phases/phase-06-weekly-review.md) | Done | 2026-10-20 | 2026-10-21 | | 440 test; golden AI 2/2 (gpt-4o); LangGraph 1.2 |
| 7 | [Monthly review](./phases/phase-07-monthly-review.md) | Done | 2026-10-21 | 2026-10-21 | M4 (MVP) ✅ | 491 test; golden AI 2/2 (gpt-4o); Recharts 3 |
| 8 | [Budget adjustment advisor](./phases/phase-08-budget-advisor.md) | Done | 2026-10-21 | 2026-10-21 | | 547 test; golden AI 4/4 (gpt-4o-mini) |
| 9 | [Flexible budget zones](./phases/phase-09-flexible-zones.md) | Done | 2026-10-21 | 2026-10-22 | | 589 test; không có AI mới (golden advisor 4/4 chạy lại) |
| 10 | [Financial Coach](./phases/phase-10-financial-coach.md) | Done | 2026-10-21 | 2026-10-22 | M5 ✅ | 654 test; golden AI 5/5 (gpt-4o), `pytest -m ai` 15/15; LangGraph 1.2.16 ToolNode |
| 11 | [Goals + Pay Yourself First](./phases/phase-11-goals-pyf.md) | Done | 2026-10-21 | 2026-10-22 | | 709 test; golden coach 7/7 (gpt-4o, + `get_goals`), `pytest -m ai` 17/17; prompt `coach_v2` |
| 12 | [Calendar & cashflow forecast](./phases/phase-12-calendar-forecast.md) | Not started | | | | |
| 13 | [Receipt OCR](./phases/phase-13-receipt-ocr.md) | Not started | | | | |
| 14 | [CSV / Excel import](./phases/phase-14-csv-import.md) | Not started | | | | |
| 15 | [Semantic search](./phases/phase-15-semantic-search.md) | Not started | | | | |
| 16 | [RAG knowledge base](./phases/phase-16-rag-knowledge.md) | Not started | | | M6 | |
| 17 | [What-if simulator](./phases/phase-17-whatif-simulator.md) | Not started | | | | Stretch |
| 18 | [Hardening & wrap-up](./phases/phase-18-hardening.md) | Not started | | | M7 | |

## Milestones

| ID | Ý nghĩa | Đạt sau phase |
|---|---|---|
| M1 | Ghi chép thủ công dùng được | 1 |
| M2 | Tracking loop hoàn chỉnh (nhập NL + AI học phân loại) | 3 |
| M3 | Budget loop hoàn chỉnh | 5 |
| M4 | Review loop — **MVP sản phẩm** | 7 |
| M5 | AI Agent (Financial Coach) | 10 |
| M6 | Full AI curriculum (Vision, Embeddings, RAG) | 16 |
| M7 | Hoàn thiện | 18 |

## Change log (thay đổi so với plan)

| Ngày | Phase | Thay đổi | Lý do |
|---|---|---|---|
| 2026-10-07 | D | Thêm `frontend-structure.md`, ADR-007 (tiền là số nguyên đồng) | Cần cho tính nhất quán giữa các phase |
| 2026-10-08 | 0 | Postgres map `5433:5432`; thêm `TEST_DATABASE_URL` (DB `pfa_test`), `LOG_LEVEL` | Port 5432 trên máy dev đã bị Postgres khác chiếm; cần DB riêng cho pytest |
| 2026-10-08 | 0 | Next.js 16.4 (thay vì 15), shadcn dùng Base UI + package `cn` | Phiên bản mới nhất của `create-next-app` / shadcn CLI tại thời điểm scaffold |
| 2026-10-08 | — | Terminal chuẩn đổi từ PowerShell sang **Git Bash**: README, `copilot-instructions.md`, khối lệnh Verify của mọi phase + template dùng cú pháp bash | Người dùng dùng Git Bash làm terminal |
| 2026-10-08 | 1 | `GET /transactions/summary` nhận cùng bộ filter với list (+ `date_from/date_to`, `by_category.kind/icon`) | Thẻ tổng trên UI phải khớp bộ lọc |
| 2026-10-08 | 1 | Category expense bắt buộc `default_spending_type`; PATCH field không cho sửa → 422; không tạo/chuyển giao dịch sang category đã ẩn | Giữ dữ liệu nhất quán, lỗi rõ ràng thay vì bỏ qua âm thầm |
| 2026-10-08 | 1 | Lỗi validate trả `{"detail": [...], "code": "validation_error"}`; thêm `npm run typecheck`, `gen:api --default-non-nullable false` | Thống nhất format lỗi; type request body đúng |
| 2026-10-13 | 2 | `TransactionDraft` trả thêm `category_id`, `occurred_on` luôn có; mã lỗi AI: `AI_NOT_CONFIGURED`/`AI_AUTH_FAILED`/`AI_RATE_LIMITED`/`AI_TIMEOUT`/`AI_UNAVAILABLE` (503), `AI_INVALID_OUTPUT` (502); `422 amount_missing` | Frontend cần id để lưu; lỗi rõ ràng theo nguyên nhân |
| 2026-10-13 | 2 | Thêm `services/amount_text.extract_amounts` + lịch tham chiếu trong prompt + cảnh báo deterministic (amount/ngày) | Giảm sai số tiền/ngày, không tin hoàn toàn vào model (ADR-005) |
| 2026-10-13 | 2 | Thông báo lưu là dòng trạng thái inline thay vì toast | Repo chưa có thư viện toast |
| 2026-10-15 | 2 | Chạy golden test (trễ vì key cũ 401); prompt NL parse lên v2 (lịch mỗi ngày một dòng, đồ uống → ăn uống) | v1 đạt ngưỡng nhưng sai "thứ 7 tuần trước" và "cafe" → `other`; v2 đạt 100% |
| 2026-10-19 | 3 | `classification_preferences` unique `(user_id, pattern)` (mỗi pattern 1 preference) thay vì kèm category/type | Tránh 2 cách phân loại mâu thuẫn cho cùng từ khoá |
| 2026-10-19 | 3 | Shortcut không gọi OpenAI chỉ cho câu đơn giản (1 khoản tiền, không nêu ngày); câu khác gọi LLM rồi hậu kiểm phân loại theo preference | Ngày / nhiều khoản vẫn cần model; phần phân loại vẫn deterministic |
| 2026-10-19 | 3 | `hit_count` tăng khi user lưu draft dùng preference (không tăng lúc parse); `POST /transactions` trả `learned_preference` | Endpoint AI không ghi DB (ADR-005); UI chỉ báo "Đã học" khi backend thực sự học |
| 2026-10-19 | 3 | Prompt NL parse lên v3 (thêm mục sở thích phân loại); `/settings` dùng tabs (`?tab=`) | Few-shot preference; tab Sở thích cạnh Danh mục theo plan |
| 2026-10-19 | 4 | Dòng nhóm của 50/30/20 / PYF lưu `jar_name = group`, actual (Phase 5) khớp theo `spending_type`; service chặn phân bổ chồng lấn (`overlapping_allocations`) | Plan chưa nói dòng nhóm khớp giao dịch thế nào; tránh đếm actual 2 lần |
| 2026-10-19 | 4 | Mỗi tháng 1 budget bất kể status (409 `budget_exists`); vượt thu nhập cần `confirm_over_income`; `savings_target` = tổng nhóm savings do service tự tính; thêm `budget_allocations.position`, `GET /budgets/jars`, preview nhận `allocations` đã chỉnh | Khớp UNIQUE `period_month`; frontend không tự cộng tiền; giữ thứ tự dòng |
| 2026-10-20 | 5 | Trạng thái dòng thêm `not_tracked` (mọi dòng nhóm savings, actual 0); `top_contributor.share` tối đa 1; totals thêm `expense_actual` (mọi khoản chi tháng), `allocated_actual`, `unbudgeted_actual`, `over_budget_count` | Plan chưa nói cách hiển thị savings, share > 1, và chi tiêu không thuộc dòng nào |
| 2026-10-20 | 5 | `/budgets/current/status` + month-summary nhận budget active **hoặc closed** (nháp → 404 `budget_not_active`); month-summary trả `budget_status`; drill-down trả `TransactionList` | Tháng đã đóng vẫn cần xem; trang chủ phân biệt "chưa có" và "nháp" |
| 2026-10-20 | 5 | Script riêng `seed_scenario` (kịch bản cố định 10/2026, `--reset`) thay vì gộp vào `seed_demo`; `/budget` tách tab Theo dõi / Kế hoạch; trang chủ `HomeDashboard` thay `HomeBudgetCta` | Số liệu kịch bản phải chính xác để test/UI; giữ editor Phase 4 nguyên vẹn |
| 2026-10-21 | 6 | `weekly_reviews.metrics` chứa cả `highlights` + tiến độ tuần (cho phép review tuần đang chạy, tuần tương lai → 422); `% thay đổi` là số nguyên; `narrative.fallback_reason`; `model = fallback_template` | Narrative chỉ được dùng số có trong metrics; UI hiển thị evidence và lý do dùng bản tự động |
| 2026-10-21 | 6 | AI lỗi → fallback ngay, chỉ retry (≤ 2) khi output không qua validate; validate thêm "action phải có điều kiện"; reflection chỉ nhận khoản chi trong tuần; pending chỉ khi tuần trước có giao dịch | Tránh 3 × timeout; giữ giọng văn không ra lệnh; dữ liệu phản tư nhất quán |
| 2026-10-21 | 6 | `agents` được gọi trực tiếp `services` + `ai/review_writer` (cập nhật `backend-components.md`); `AppNav` bọc `<Suspense>` | Graph review cần collect/persist qua services; route động đầu tiên làm `usePathname()` thành dữ liệu runtime (Cache Components) |
| 2026-10-21 | 7 | `MonthlyReviewMetrics` giữ tên chung `income`/`expense`/`net` + `saved`; so sánh tháng trước trải phẳng (`income_change_pct`, `saved_change`…); % tỉ trọng ở `spending_type_pct` (1 chữ số); thêm `regular_expense*`, `irregular_change`, `increase_driver` | Dùng chung schema/fallback/UI với review tuần; cần tín hiệu deterministic "tăng do khoản một lần" để AI không quy kết thói quen |
| 2026-10-21 | 7 | Validate tháng: chi tăng chủ yếu do khoản bất thường → phải nêu khoản đó; cụm cấm thêm "kém kỷ luật", "ngân sách sai", `adjust_budget`… (áp cho cả tuần); số được phép / prompt bỏ ID theo tên khoá | Guardrail mục 4.3; review không đưa verdict trước Phase 8 |
| 2026-10-21 | 7 | Phản tư tuần thuộc tháng = review tuần có Thứ Hai trong tháng; thêm `/reviews/monthly` (index) và trang giữ chỗ `/budget/advice`; thêm `recharts` + `react-is` | Quy tắc gán tuần rõ ràng; CTA điều hướng được trước khi có Phase 8 |
| 2026-10-21 | 8 | Bước 2 decision tree = **tổng** giao dịch `irregular` hoặc 1 giao dịch đơn lẻ ≥ 60% phần vượt; lịch sử 3 tháng **tính cả tháng đang xét** (tháng có dữ liệu = có giao dịch trong phạm vi dòng); CV population; advice cho mọi dòng trừ nhóm `savings` (kể cả hũ / dòng nhóm, theo `allocation_scope` Phase 4) | Plan chưa định nghĩa "có giao dịch irregular" (1 khoản nhỏ không nên biến cả dòng thành one_off) và "lịch sử"; mapping hũ đã rõ từ Phase 4 |
| 2026-10-21 | 8 | `budget_advice` thêm `narrative` JSONB, `model`, `applied_month`, `dismiss_reason`; evidence thêm `rule`, `*_pct`, `one_off_transaction`, `history_median`…; generate nhận `regenerate`/`today`, yêu cầu budget active/closed, không tạo lại advice đã accepted/dismissed; accept thêm `confirm_over_income`, trả thêm `budget{created}`; `on_track` dùng template (không gọi AI) | UI cần 3 tầng + nguồn văn bản + kết quả quyết định; AI/template chỉ được trích số có sẵn; tái dùng quy tắc vượt thu nhập Phase 4 |
| 2026-10-21 | 8 | Accept sửa dòng tháng đích **tại chỗ** (`budget_service.set_allocation_planned`, giữ id) thay vì PATCH thay toàn bộ phân bổ; `copy_from_previous_month` tách `_copy_budget` (không commit) để tạo nháp + sửa dòng + đánh dấu advice trong 1 commit | Atomic, không làm mất advice (FK cascade) của tháng đích |
| 2026-10-22 | 9 | Zone gắn vào `GET /budgets/{id}/status` (plan ghi `/actuals` — endpoint Phase 5 thực tế là `/status`); ngưỡng auto chỉ lưu khi user bấm tính lại / chuyển sang auto (NULL = chưa có zone, không tự tính khi tạo/copy/đọc); history = 6 tháng trước tháng ngân sách, cần ≥ 3 tháng có giao dịch trong phạm vi; nhóm `irregular` luôn % dự phòng; early warning dung sai 10 điểm % như `pace_status`, độc lập với zone | Giữ nguyên hành vi advisor Phase 8 khi chưa bật vùng ("planned nếu chưa có zone"), GET không ghi DB; plan chưa định nghĩa "đáng kể" / tháng trống |
| 2026-10-22 | 9 | Response thêm `calculated`, `early_warning_message`, `expected_to_date`, `auto{basis, history, mean, std, suggested, stale}`; PATCH auto không nhận ngưỡng (422), budget đã đóng → 409; sửa/copy budget giữ vùng manual, giữ cache auto khi planned không đổi; evidence advisor thêm `zone`; thêm UI `tooltip` (shadcn) | UI giải thích được ngưỡng và biết khi nào cần tính lại; không mất cấu hình vùng khi sửa planned (PATCH thay toàn bộ dòng) |
| 2026-10-22 | 10 | `chat_messages` thêm cột `evidence` JSONB; metadata thêm `prompt_version`/`llm_calls`/`tool_rounds`/`latency_ms`/`guard_problems`; mỗi lượt lưu 1 user + 1 assistant (tool trace nằm trong assistant, không ghi message role `tool`); `GET /coach/sessions` trả `{items}`; `POST …/messages` nhận `today`, response có `session` | Refresh vẫn thấy bảng "Dữ liệu đã dùng"; theo dõi token / chi phí / guard; thống nhất quy ước danh sách + `today` như review / advice |
| 2026-10-22 | 10 | Graph thêm node `scope_check`: câu hỏi đầu tư / chứng khoán / crypto / thuế **và yêu cầu ghi dữ liệu** → template deterministic, không gọi model; `guard_status` thêm `rewritten`, `fallback`, `refused_write_request`; guard còn fail sau 1 lần viết lại → câu trả lời liệt kê evidence | Từ chối ổn định, không tốn token; read-only kiểm chứng được bằng test; không bao giờ trả số bịa |
| 2026-10-22 | 10 | `coach_service.send_message` nhận `runner` (router truyền `coach_graph.run_coach`); model gọi qua `openai_client.chat_with_tools` (không thêm `langchain-openai`); timeout → `AI_TIMEOUT` (503) thay vì `AI_UNAVAILABLE` của test case 8 | Quy tắc phụ thuộc (`services` không import `agents`), mọi lời gọi OpenAI qua `openai_client`; giữ mã lỗi AI của Phase 2 |
| 2026-10-22 | 10 | `get_category_trend` mặc định kết thúc ở tháng đã trọn gần nhất, "biến động" = population std (đồng) + hạng; `get_budget_advice` chỉ đọc advice đã có (không generate) | Plan chưa định nghĩa "biến động" / tháng cuối; tháng đang chạy làm méo trend; generate advice là thao tác ghi |
| 2026-10-22 | 11 | `months_remaining` = tính cả tháng hiện tại, không tính tháng đến hạn (tối thiểu 1, quá hạn 0); `suggested_monthly_saving` không vượt phần còn thiếu, quá hạn → toàn bộ còn thiếu; đủ tiền → tự `achieved`, thiếu lại → `active` | Khớp "deadline sau 5 tháng → 5" của test case 1; plan chia cho 0 khi quá hạn; test case 2 cho phép "status đạt" |
| 2026-10-22 | 11 | `GET /goals` trả `{items, total_suggested_monthly_saving}`; `GoalRead` thêm `progress_pct`, `overdue`, `contribution_count`, `last_contributed_on`; PATCH nhận `target_amount`; mọi route goal nhận `?today=`; thêm `POST/DELETE /goals/{id}/contributions` (góp thủ công / sửa nhầm), `GET /goals/unallocated-incomes` | Quy ước danh sách của repo; frontend không tự tính %; kịch bản UI cần góp 8.000.000 có sẵn và nút "Phân bổ từ thu nhập" |
| 2026-10-22 | 11 | `POST /goals/pyf-proposal` nhận `items` / `budget_savings_amount` để tính lại số user chỉnh (+ `warnings`, `valid`); một thu nhập chỉ xác nhận phân bổ 1 lần (409 `income_already_allocated`); khoản góp chỉ cho goal active, ≤ phần còn thiếu; `budget_savings_amount` không lưu | Frontend không tự tính tiền; chống trích trùng; plan không có bảng cho tiết kiệm ngân sách |
| 2026-10-22 | 11 | FK `goal_contributions.income_transaction_id` `ON DELETE SET NULL`; `transaction_service` chặn đổi thu nhập đã phân bổ thành khoản chi (409) / giảm dưới tổng đã phân bổ (422); `MAX_AMOUNT` chuyển sang `schemas/common.py` | Giữ tiến độ goal khi xoá giao dịch; dữ liệu nhất quán; tránh import vòng schema |
| 2026-10-22 | 11 | Coach prompt `coach_v2.md` (+ `get_goals`); "mục tiêu", "khoản góp" là đối tượng ghi → từ chối kèm link `/goals` | Đăng ký tool theo gợi ý handoff Phase 10; Coach vẫn chỉ đọc |

## Câu hỏi mở xuyên suốt

- Có cần khái niệm "tài khoản/ví" (tiền mặt, ngân hàng, thẻ tín dụng) không? Ảnh hưởng tới forecast (Phase 12) và import (Phase 14). Hiện: không.
- Chuyển khoản nội bộ / trả nợ thẻ tín dụng không phải chi tiêu — xử lý thế nào khi import (Phase 14)?
