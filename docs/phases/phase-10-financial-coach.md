# Phase 10 — Financial Coach

| | |
|---|---|
| **ID** | `phase-10-financial-coach` |
| **Trạng thái** | Not started |
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

- [ ] T1 Migration + ORM/Pydantic schemas cho `chat_sessions`, `chat_messages`
- [ ] T2 `CoachToolRegistry` + 5 read-only tools hiện có
- [ ] T3 `coach_v1.md` prompt + `coach_graph` agent ↔ ToolNode loop, giới hạn 6 vòng
- [ ] T4 `response_guard` deterministic + refusal template ngoài phạm vi
- [ ] T5 `coach_service` lưu user/assistant/tool trace, token/cost logging
- [ ] T6 Router `/api/v1/coach/*` + API tests persistence/error handling
- [ ] T7 Golden AI tests `@pytest.mark.ai` cho "Tao nên giảm khoản nào?"
- [ ] T8 UI `/coach` chat page + session list
- [ ] T9 UI `ToolTracePanel` + `EvidenceTable`
- [ ] T10 Frontend error/loading states + suggested prompt chips
- [ ] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-10: financial coach`

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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` mặc định xanh không cần `OPENAI_API_KEY`; test AI chỉ chạy bằng `pytest -m ai`
- [ ] Coach tools read-only, không gọi repository trực tiếp từ graph/tool ngoài service layer
- [ ] Answer không bịa số, không dùng banned phrases trong golden tests
- [ ] Token/cost/latency được log trong `chat_messages.metadata`
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [ ] Commit `phase-10: financial coach`

## 8. Rủi ro / câu hỏi mở

- LangGraph/LangChain API thay đổi nhanh; cần pin version và ghi version thực tế ở Handoff notes.
- Plain JSON làm user phải chờ graph chạy xong; nếu latency > 8–10 giây, Phase 18 nên cân nhắc SSE.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
