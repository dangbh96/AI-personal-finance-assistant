# Phase 10 — Financial Coach

| | |
|---|---|
| **ID** | `phase-10-financial-coach` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 8 |
| **Mở khoá** | Phase 16 |
| **Milestone** | **M5 — AI Agent** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 8
2. [glossary.md](../product/glossary.md) — `coach`, `BudgetAdvice`, `verdict`
3. [vision.md](../product/vision.md) — AI 3 tầng, không phán xét, không quyết định thay user
4. [brainstorm-original.md](../product/brainstorm-original.md#12-financial-coach) — ví dụ "Tao nên giảm khoản nào?"
5. [ai-architecture.md](../architecture/ai-architecture.md) — `coach_graph`, ToolNode, `response_guard`, tối đa 6 vòng tool
6. [backend-components.md](../architecture/backend-components.md) — `agents/`, `agents/tools/`, tools bọc services
7. [data-model.md](../architecture/data-model.md) — `chat_sessions`, `chat_messages` (bảng thực tế plural snake_case)
8. [sequences.md](../architecture/sequences.md#4-financial-coach-tao-nên-giảm-khoản-nào)
9. [frontend-structure.md](../architecture/frontend-structure.md) — route `/coach`
10. ADR [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [006](../architecture/decisions/ADR-006-langgraph-for-workflows.md)

Trạng thái code giả định: Phase 8 đã Done; có transactions, categories, budgets, budget_allocations, budget_advice; `analytics_service`, `budget_service`, `advisor_rules` đã tính được summary, variance, trend và evidence deterministic.

## 2. Mục tiêu & giá trị cho user

User hỏi bằng tiếng Việt về chi tiêu/budget và nhận câu trả lời dựa trên dữ liệu thật, có evidence rõ ràng, giọng trung lập. Phase này biến các phân tích rời rạc của Phase 5–8 thành Financial Coach gọi tool đọc dữ liệu, giải thích theo Observation → Explanation → Action, nhưng không tự sửa dữ liệu hay quyết định thay user.

## 3. Scope

**In scope**
- `coach_graph` bằng LangGraph: node `agent` ↔ `ToolNode`, node `response_guard`, tối đa 6 vòng tool call / user message.
- LangChain `@tool` read-only bọc services: `get_spending_summary`, `get_budget_status`, `get_category_trend`, `get_budget_advice`, `get_recent_reviews`.
- Tool registry mở rộng để Phase 11/15/16/17 chỉ thêm tool: `get_goals`, `search_transactions`, `search_knowledge`, `simulate`.
- Bảng `chat_sessions`, `chat_messages` lưu hội thoại, tool trace, model, token/cost metadata.
- API chat **plain JSON** trả final assistant message + visible tool trace/evidence table. Không SSE ở Phase 10 để dễ test deterministic; có thể nâng cấp sau.
- UI `/coach` full page: danh sách session, khung chat, bảng "Dữ liệu đã dùng" và tool trace.
- Golden AI test cho "Tao nên giảm khoản nào?" kiểm tra tool call, số liệu từ tool output, suggestion có điều kiện, không chứa cụm từ cấm.

**Out of scope**
- Tạo/sửa/xoá giao dịch, budget, budget advice từ Coach; Coach chỉ đưa link tới màn hình tương ứng.
- Streaming SSE/WebSocket.
- RAG kiến thức tài chính (Phase 16), semantic search (Phase 15), simulator (Phase 17), tool `get_goals` nếu Phase 11 chưa có.
- Tư vấn đầu tư/chứng khoán/crypto/thuế.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`chat_sessions`: `id UUID PK`, `user_id UUID NULL`, `title TEXT`, `created_at`, `updated_at`.
- `title` sinh từ user message đầu tiên, ví dụ `Nên giảm khoản nào`.
- Index `(updated_at DESC)`.

`chat_messages`: `id UUID PK`, `session_id UUID FK chat_sessions(id) ON DELETE CASCADE`, `role TEXT CHECK role IN ('user','assistant','tool')`, `content TEXT`, `tool_calls JSONB`, `metadata JSONB`, timestamps.
- `tool_calls`: `[{name,args,result_summary,evidence_refs,latency_ms}]`.
- `metadata`: `{model,input_tokens,output_tokens,total_tokens,estimated_cost_vnd,guard_status}`; không log API key/raw prompt dài.
- Index `(session_id, created_at)`.

Không thay đổi bảng nghiệp vụ khác; mọi tool đọc qua service/repository hiện có.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/coach/sessions` | List chat sessions | `?limit=20` | `[{id,title,updated_at,last_message_preview}]` |
| POST | `/api/v1/coach/sessions` | Tạo session | `{title?: string}` | `{id,title,created_at}` |
| GET | `/api/v1/coach/sessions/{session_id}` | Lấy session + messages | — | `{id,title,messages:[...]}` |
| PATCH | `/api/v1/coach/sessions/{session_id}` | Đổi title | `{title}` | `{id,title}` |
| DELETE | `/api/v1/coach/sessions/{session_id}` | Xoá session | — | `204` |
| POST | `/api/v1/coach/sessions/{session_id}/messages` | Gửi message, chạy `coach_graph` | `{content}` | `{user_message,assistant_message,tool_trace,evidence,guard_status}` |

Module chính:
- `app/agents/coach_graph.py`: build graph, bind tools, `max_tool_rounds=6`, retry guard tối đa 1 lần.
- `app/agents/tools/registry.py`: `CoachToolRegistry`; missing future tool bị bỏ qua an toàn.
- `app/agents/tools/finance_tools.py`: `@tool` gọi `analytics_service`, `budget_service`, `budget_advice_service`, `review_service`.
- `app/services/coach_service.py`: persistence + invoke graph + chuẩn hoá response.
- `app/core/ai_usage.py`: log token/cost/latency.

### 4.3 AI

Model đọc từ env:
- `OPENAI_MODEL_SMART` (mặc định `gpt-4o`) cho `coach_graph`.
- `OPENAI_MODEL_FAST` (mặc định `gpt-4o-mini`) chỉ dùng nếu sau này cần guard phụ.

Tool schemas:
```python
class SpendingSummaryInput(BaseModel):
    from_date: date
    to_date: date
    group_by: Literal["category", "spending_type"] = "category"

class SpendingSummaryItem(BaseModel):
    category_slug: str | None
    category_name: str | None
    spending_type: Literal["essential", "non_essential", "irregular"] | None
    total: int
    transaction_count: int

class SpendingSummaryOutput(BaseModel):
    income_total: int
    expense_total: int
    net: int
    items: list[SpendingSummaryItem]

class CategoryTrendInput(BaseModel):
    months: int = Field(default=3, ge=2, le=12)
    category_slug: str | None = None

class CategoryTrendItem(BaseModel):
    category_slug: str
    category_name: str
    totals_by_month: dict[str, int]
    latest_total: int
    delta_vs_previous: int
    volatility_rank: int
```

Prompt `backend/app/ai/prompts/coach_v1.md`:
1. Financial Coach tiếng Việt, xưng "bạn".
2. Chỉ dùng số từ tool outputs; nếu thiếu dữ liệu phải gọi tool hoặc nói chưa đủ dữ liệu.
3. Format: `Quan sát` → `Vì sao` → `Bạn có thể cân nhắc`; kèm 2–4 bullet evidence.
4. Guardrails: read-only; không đầu tư/chứng khoán/crypto/thuế; cấm `bạn tiêu quá nhiều`, `lãng phí`, `bạn phải`, `ngay lập tức`.
5. Ngoài phạm vi: từ chối ngắn và gợi ý câu hỏi trong phạm vi app.

`response_guard` deterministic:
- Trích số tiền trong answer, normalize VND, đối chiếu `evidence`.
- Check banned phrases + tone ra lệnh.
- Nếu có khuyến nghị nhưng thiếu điều kiện (`có thể`, `nếu bạn muốn`, `cân nhắc`) → rewrite 1 lần.
- Nếu user hỏi đầu tư/crypto/chứng khoán/thuế → refusal template.

### 4.4 Frontend

- Route `/coach` full page, không phải popup.
- Components: `CoachSessionList`, `CoachChatWindow`, `CoachMessageBubble`, `ToolTracePanel`, `EvidenceTable`, `SuggestedQuestionChips`.
- Loading: "Coach đang đọc dữ liệu..."; sau response hiển thị answer + evidence.
- Tool trace hiển thị tên tool, args, số dòng kết quả, latency; không hiển thị raw prompt.
- Suggested prompts: "Tháng này khoản nào vượt budget?", "Tao nên giảm khoản nào?", "Có khoản bất thường nào không?".

## 5. Task breakdown

- [x] T1 Migration + ORM/Pydantic schemas cho `chat_sessions`, `chat_messages`
- [x] T2 `CoachToolRegistry` + 5 read-only tools hiện có
- [x] T3 `coach_v1.md` prompt + `coach_graph` agent ↔ ToolNode loop, giới hạn 6 vòng
- [x] T4 `response_guard` deterministic + refusal template ngoài phạm vi
- [x] T5 `coach_service` lưu user/assistant/tool trace, token/cost logging
- [x] T6 Router `/api/v1/coach/*` + API tests persistence/error handling
- [x] T7 Golden AI tests `@pytest.mark.ai` cho "Tao nên giảm khoản nào?"
- [x] T8 UI `/coach` chat page + session list
- [x] T9 UI `ToolTracePanel` + `EvidenceTable`
- [x] T10 Frontend error/loading states + suggested prompt chips
- [x] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-10: financial coach`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend && alembic upgrade head && ruff check . && pytest
export OPENAI_API_KEY="sk-..." && pytest -m ai
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run gen:api && npm run lint && npm run dev
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Seed tháng 2026-09: food 4.200.000, shopping 3.800.000, entertainment 1.100.000; gọi `get_category_trend(months=3)` | Output có `food.latest_total=4200000`, `shopping.latest_total=3800000`, rank biến động đúng fixture |
| 2 | Budget 2026-09: shopping planned 2.000.000, actual 3.800.000 | `get_budget_status` trả variance 1.800.000, không tự sửa budget |
| 3 | POST message vào session mới | Lưu 1 user + 1 assistant message; response có `tool_trace` |
| 4 | User hỏi "Mua cổ phiếu nào tuần này?" | Refusal ngắn, không khuyến nghị đầu tư, `guard_status="refused_out_of_scope"` |
| 5 | Guard nhận answer chứa "bạn tiêu quá nhiều" | Fail, yêu cầu rewrite trong unit test |
| 6 | Guard nhận answer nêu 9.999.999 không có trong evidence | Fail vì số không nằm trong tool outputs |
| 7 | `@pytest.mark.ai` golden "Tao nên giảm khoản nào?" | Tool `get_category_trend` được gọi; answer cite 4.200.000/3.800.000; có gợi ý điều kiện; không banned phrases |
| 8 | OpenAI timeout giả lập | API trả 503 `{code:"AI_UNAVAILABLE"}`, user message vẫn lưu |

**Kịch bản thao tác UI**
1. Mở `/coach`, tạo session mới, nhập "Tao nên giảm khoản nào?".
2. Thấy câu trả lời có Quan sát/Vì sao/Gợi ý; bảng evidence liệt kê category, tháng, số tiền.
3. Mở Tool trace → thấy `get_category_trend` và `get_budget_status` với args rõ ràng.
4. Refresh trang → lịch sử chat và tool trace vẫn còn.
5. Hỏi "Tự giảm budget mua sắm giúp tao" → Coach từ chối ghi dữ liệu và đưa link `/budget` hoặc `/budget/advice`.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` mặc định xanh không cần `OPENAI_API_KEY`; test AI chỉ chạy bằng `pytest -m ai`
- [x] Coach tools read-only, không gọi repository trực tiếp từ graph/tool ngoài service layer
- [x] Answer không bịa số, không dùng banned phrases trong golden tests
- [x] Token/cost/latency được log trong `chat_messages.metadata`
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [x] Commit `phase-10: financial coach agent`

## 8. Rủi ro / câu hỏi mở

- LangGraph/LangChain API thay đổi nhanh; cần pin version và ghi version thực tế ở Handoff notes.
  - **Đã chốt:** `langgraph` 1.2.16 (pin `>=1.2,<1.3` trong `pyproject.toml`), `langgraph-prebuilt` 1.1.1 (`ToolNode` + `wrap_tool_call`), `langchain-core` 1.6.12 (`@tool`, `convert_to_openai_tool`) — đi kèm langgraph, không thêm `langchain-openai` (model gọi qua `ai/openai_client`).
- Plain JSON làm user phải chờ graph chạy xong; nếu latency > 8–10 giây, Phase 18 nên cân nhắc SSE.
  - **Đo được:** 2 lời gọi model / câu hỏi điển hình, 3,5–8 giây (gpt-4o), ~4.000–5.600 token ≈ 310–430 đ; khi guard bắt viết lại ~5 giây và ~7.800 token. Chưa vượt 10 giây trong smoke test.
- Hạng biến động dùng độ lệch chuẩn **tuyệt đối** (đồng) nên danh mục chi lớn (Ăn uống) dễ xếp hạng cao hơn danh mục nhỏ biến động mạnh theo %. Có thể bổ sung CV (%) nếu cần (Phase 17 / 18).
- Phân loại "yêu cầu ghi dữ liệu" và "ngoài phạm vi" là luật từ khoá (có dấu) — câu viết không dấu / diễn đạt lạ có thể lọt qua; khi đó model vẫn bị prompt + guard (cấm "tôi đã điều chỉnh…") giữ read-only vì không có tool ghi.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22 (bắt đầu 2026-10-21)
- **Đã làm:**
  - **Migration** `20261022_cd108ee2d244_financial_coach`: `chat_sessions` (`user_id` NULL, `title`, index `updated_at`) + `chat_messages` (FK `ON DELETE CASCADE`, CHECK `role`, `tool_calls` / `evidence` / `metadata` JSONB, index `(session_id, created_at)`). ORM `models/chat.py` (`ChatSession`, `ChatMessage.meta` ↔ cột `metadata`; `created_at` / `updated_at` đặt từ Python), enum `ChatRole`, `CoachGuardStatus`. Schemas `schemas/coach.py` (input / output 5 tool theo plan § 4.3 + thêm field, tool trace, evidence, metadata, API).
  - **Deterministic (services, không AI):**
    - `insight_service`: `get_spending_summary` (thu / chi / net, theo danh mục hoặc spending_type, `share_pct`; khoảng ≤ 366 ngày), `get_category_trend` (N = 2–12 tháng, mặc định kết thúc ở **tháng đã trọn gần nhất**; `totals_by_month`, `latest_total`, `previous_total`, `delta_vs_previous(_pct)`, `average`, `volatility` = population std (đồng, dùng `zone_service.history_stats`), `volatility_rank` (std lớn nhất = 1; hoà → tháng cuối lớn hơn, rồi slug), `irregular_total`, `most_volatile`), `get_budget_status` (Budget vs Actual + vùng rút gọn; tháng chưa có ngân sách active/closed → `available=false` + lý do), `get_budget_advice` (advice **đã có**, mặc định tháng gần nhất có advice; không tạo mới), `get_recent_reviews` (review tuần / tháng đã tạo). Hàm thuần `build_trend_items`, `trend_months`, `share_pct`, `change_pct`.
    - `coach_guard`: `classify_request` (ngoài phạm vi: cổ phiếu / chứng khoán / crypto / đầu tư / thuế…; yêu cầu ghi: động từ ghi + đối tượng + "giúp/hộ/tự…" hoặc mở đầu bằng động từ, trừ câu có ý hỏi), `refusal_answer` (link `/budget`, `/budget/advice`, `/transactions`), `allowed_numbers`, `check_answer` (số ⊆ output tool, cụm cấm + tự nhận đã sửa dữ liệu, tên kỹ thuật, 3 phần + điều kiện), `fallback_answer`, `make_title`.
    - `coach_evidence`: dòng evidence từ output tool, `select_evidence` (giữ dòng có số tiền được trích, mã E1…, `evidence_refs` từng tool call), `summarize_result`.
    - `coach_service`: CRUD session (preview message cuối, số message), `send_message` (commit user message → `runner` → lưu assistant message + trace + evidence + metadata; tự đặt tiêu đề từ câu đầu).
  - **AI / agent:** `ai/openai_client.chat_with_tools` (+ seam `_chat_tools`, map lỗi `AI_*` như cũ), `ai/coach_prompt.py` + prompt `prompts/coach_v1.md`, `core/ai_usage.py` (`UsageTotals`, `estimate_cost_vnd`, `log_usage`). `agents/tools/registry.py` (`CoachToolRegistry`, `ToolRecorder`, `COACH_TOOL_NAMES` gồm tool tương lai), `agents/tools/finance_tools.py` (5 `@tool` read-only chỉ gọi `insight_service`), `agents/coach_graph.py` (`scope_check` → `agent` ⇄ `ToolNode` (≤ 6 vòng, vòng cuối `tool_choice="none"`) → `response_guard` (viết lại ≤ 1 lần → fallback), `run_coach`).
  - **API** `api/routers/coach.py`: `GET/POST /coach/sessions` (`?limit=1..100`), `GET/PATCH/DELETE /coach/sessions/{id}`, `POST /coach/sessions/{id}/messages` `{content, today?}` → `{session, user_message, assistant_message, tool_trace, evidence, guard_status}`. Lỗi: `chat_session_not_found` (404), `validation_error` (422), `AI_*` (503 / 502) — câu hỏi vẫn lưu.
  - **Frontend:** `/coach` (`CoachPage`, `CoachSessionList`, `CoachChatWindow`, `CoachMessageBubble`, `CoachAnswerText`, `EvidenceTable`, `ToolTracePanel`, `SuggestedQuestionChips`), `lib/coach.ts` (câu gợi ý, nhãn guard / tool, gợi ý theo mã lỗi), type mới trong `lib/api.ts`, nav "Financial Coach" bật. `gen:api` chạy lại (chỉ thêm type).
  - **Test:** 654 pass (+65): `tests/unit/test_coach_guard.py` (test case 4–6, phân loại câu hỏi, số từ khoá tháng / câu hỏi / ID, cấu trúc, tên kỹ thuật, fallback / template qua guard, tiêu đề), `tests/unit/test_coach_insights.py` (trend + hạng biến động / hoà / tháng trước = 0, evidence, tóm tắt, chi phí token), `tests/api/test_coach_tools.py` (test case 1, 2 trên DB, summary, advice / review thật, registry + schema tool), `tests/api/test_coach.py` (CRUD session, test case 3 với model giả gọi 2 tool, không sửa budget, lịch sử gửi kèm, test case 4 + yêu cầu ghi không gọi AI, guard viết lại / fallback, giới hạn 6 vòng, lỗi tool trả về model, test case 8: timeout → 503 `AI_TIMEOUT`, mất kết nối → 503 `AI_UNAVAILABLE`, chưa cấu hình → 503, user message còn). Dữ liệu `tests/coach_dataset.py`.
  - **Golden AI** `tests/ai_golden/test_coach.py`: **5/5 pass** (`gpt-4o-2024-08-06`, cả 3 câu có AI đều `guard_status = passed` ngay lần đầu): "Tao nên giảm khoản nào?" gọi `get_category_trend` + `get_budget_status`, trích 4.200.000 / 3.800.000, gợi ý có điều kiện; "Tháng này khoản nào vượt budget?"; chống giọng phán xét; từ chối cổ phiếu / "Tự giảm budget mua sắm giúp tao". Toàn bộ `pytest -m ai`: **15/15 pass**.
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev), `ruff check .`, `ruff format --check .`, `pytest` (654), `pytest -m ai` (15), `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh; `npm run start` → `/`, `/coach`, `/budget?month=2026-10`, `/budget/advice`, `/transactions`, `/reviews/monthly/2026-10`, `/settings` trả 200. Smoke API + UI với **DB tạm `pfa_smoke`** (seed_demo 05–09/2026 + seed_scenario 10/2026, đã xoá; DB dev chỉ được migrate): hội thoại thật 5 câu (2 tool, guard passed; "Có khoản bất thường nào không?" guard viết lại 1 lần rồi pass; 2 câu từ chối không gọi AI), ngân sách không đổi; kịch bản UI mục 6: tạo cuộc trò chuyện bằng chip / ô nhập, thấy Quan sát / Vì sao / Bạn có thể cân nhắc + bảng "Dữ liệu đã dùng" (danh mục, tháng, số tiền), mở Tool trace thấy `get_category_trend` (`months=3`) và `get_budget_status`, refresh vẫn còn lịch sử + trace, "Tự giảm budget mua sắm giúp tao" → từ chối kèm link `/budget`, `/budget/advice`; đổi tên / xoá session; backend tắt / thiếu key → khung lỗi + "Gửi lại".
- **Lệch so với plan (và lý do):**
  - Thêm cột `chat_messages.evidence` (JSONB) để refresh trang vẫn hiện bảng "Dữ liệu đã dùng" (plan chỉ có `tool_calls` + `metadata`). Metadata thêm `prompt_version`, `llm_calls`, `tool_rounds`, `latency_ms`, `guard_problems`; tool trace thêm `result_count`, `error`. Role `tool` có trong CHECK nhưng Phase 10 không ghi message tool riêng (trace nằm trong assistant message) → mỗi lượt đúng 1 user + 1 assistant (test case 3).
  - `GET /coach/sessions` trả `{items: [...]}` (quy ước danh sách của repo) thay vì mảng trần; summary thêm `message_count`, `created_at`. `POST /messages` nhận thêm `today` (như các endpoint review / advice) và response có `session`.
  - Graph thêm node `scope_check` trước `agent`: câu hỏi đầu tư / crypto / thuế và **yêu cầu ghi dữ liệu** trả template deterministic, không gọi model (`guard_status = refused_out_of_scope | refused_write_request`). Guard status thêm `rewritten`, `fallback`.
  - Orchestration: `coach_service.send_message` nhận `runner` do router truyền (`coach_graph.run_coach`) vì `services` không được import `agents`; graph gọi model qua `openai_client.chat_with_tools` (không thêm `langchain-openai`).
  - Test case 8: timeout map sang `AI_TIMEOUT` (503) theo quy ước Phase 2; lỗi mạng / 5xx là `AI_UNAVAILABLE` (503) — cả hai đều 503 và giữ câu hỏi.
  - Trend mặc định kết thúc ở tháng đã trọn gần nhất (test case 1: seed 09/2026 → `latest_total` là tháng 9); "biến động" = population std theo đồng.
  - Index `chat_sessions(updated_at)` dạng btree thường (quét ngược cho DESC) thay vì `updated_at DESC` — tương đương, `alembic check` sạch.
- **Nợ kỹ thuật / TODO để lại:**
  - Plain JSON, chưa stream (SSE ở Phase 18 nếu cần). Không huỷ được câu hỏi đang chạy.
  - Lịch sử gửi model chỉ gồm nội dung user / assistant (không gồm output tool cũ) → câu hỏi nối tiếp cần gọi lại tool để trích số; guard không cho dùng số từ lượt trước.
  - Tập số được phép là tập giá trị (không theo ngữ cảnh) như Phase 6–8; model có thể ghép đúng số nhưng sai nhãn (vd số của tháng khác) mà guard không bắt. Model đôi khi suy đoán nguyên nhân ("có thể do thói quen…") — prompt cấm phán xét nhưng chưa cấm suy đoán.
  - Phân loại ngoài phạm vi / yêu cầu ghi bằng từ khoá có dấu (xem mục 8). "đầu tư" bị từ chối cả khi nghĩa rộng ("đầu tư cho bản thân").
  - Chưa có `user_id` thực (ADR-004), chưa giới hạn số session / message, chưa rate limit; chi phí token là ước tính theo bảng giá cố định trong `core/ai_usage.py` (tỉ giá 26.000).
  - Nếu kết nối đứt sau khi backend đã nhận câu hỏi, UI bỏ bong bóng tạm nhưng câu hỏi có thể đã được lưu (thấy lại khi tải lại). Chưa có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_coach_guard.py tests/unit/test_coach_insights.py tests/api/test_coach.py tests/api/test_coach_tools.py -q)`
  - `(cd backend && pytest -m ai tests/ai_golden/test_coach.py -s)`
  - `curl -s -X POST localhost:8000/api/v1/coach/sessions -H "Content-Type: application/json" -d '{}'`
  - `curl -s -X POST localhost:8000/api/v1/coach/sessions/<id>/messages -H "Content-Type: application/json" -d '{"content":"Tao nên giảm khoản nào?","today":"2026-10-21"}'`
  - UI: `/coach?today=2026-10-21` (với dữ liệu `seed_scenario`).
- **Gợi ý cho phase tiếp theo (Phase 11 — Goals + Pay Yourself First):**
  - Thêm tool `get_goals`: viết factory trong `agents/tools/finance_tools.py` (hoặc file mới `goal_tools.py`) gọi `goal_service.list_goal_status()` qua một hàm trong `services/insight_service` (hoặc `goal_service`) trả Pydantic output, rồi `registry.register("get_goals", factory)` trong `default_registry()` — tên đã có trong `COACH_TOOL_NAMES`, không cần sửa graph. Thêm dòng evidence trong `coach_evidence.evidence_rows` + `summarize_result` cho output mới, và một dòng gợi ý chọn tool trong `prompts/coach_v1.md` (đổi tên `coach_v2.md` + `PROMPT_VERSION` nếu sửa prompt, chạy lại golden).
  - Tool phải read-only: tạo contribution / xác nhận PYF là thao tác ghi → Coach chỉ dẫn link `/goals`; nếu thêm, cập nhật `coach_guard.WRITE_OBJECTS` (vd "mục tiêu" → `/goals`) và `LINK_LABELS`.
  - Dòng nhóm `savings` hiện `status = not_tracked`, actual 0 trong `get_budget_status` — khi Phase 11 nối Goals/PYF, cập nhật `insight_service.get_budget_status` nếu cần hiển thị tiến độ tiết kiệm.
  - DB dev: đã `alembic upgrade head` (có `chat_sessions` / `chat_messages`, chưa có hội thoại nào).
