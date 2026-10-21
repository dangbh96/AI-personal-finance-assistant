# AI Architecture

## 1. Bản đồ tác vụ AI

| Tác vụ | Phase | Kỹ thuật | Model mặc định | Output |
|---|---|---|---|---|
| Parse câu nhập giao dịch | 2 | Structured Outputs (Pydantic → JSON schema) | `gpt-4o-mini` | `TransactionDraft` |
| Phân loại category × spending_type | 2, 3 | Structured Outputs + few-shot từ `classification_preference`; exact-match preference → deterministic | `gpt-4o-mini` | `ClassificationSuggestion` (kèm `confidence`, `reason`) |
| Parse câu sở thích phân loại ("Tao coi giày là thiết yếu") | 3 | Structured Outputs | `gpt-4o-mini` | `PreferenceDraft` |
| Weekly / Monthly review narrative | 6, 7 | LangGraph workflow, input là metrics đã tính sẵn | `gpt-4o` | `ReviewNarrative` |
| Giải thích Budget advice | 8 | Structured Outputs, input là `evidence` deterministic; validate + template dự phòng | `gpt-4o-mini` (`OPENAI_MODEL_FAST`) | `BudgetAdviceExplanation` (3 tầng) |
| Financial Coach | 10, 16 | LangGraph ReAct agent + function calling (LangChain tools) | `gpt-4o` | Chat message + tool calls |
| Đọc hoá đơn | 13 | Vision input + Structured Outputs | `gpt-4o` | `ReceiptExtraction` |
| Phân loại hàng loạt khi import | 14 | Batch classify (gom 20 dòng / request) | `gpt-4o-mini` | `list[ClassificationSuggestion]` |
| Embedding giao dịch | 15 | `text-embedding-3-small` (1536 dim) | — | vector |
| RAG kiến thức tài chính | 16 | Chunk + embed + pgvector similarity + trích nguồn | `gpt-4o` | Câu trả lời có citation |
| Diễn giải What-if | 17 | Structured Outputs trên kết quả mô phỏng | `gpt-4o-mini` | Narrative |

Tên model đọc từ env (`OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`) — không hard-code.

## 2. Nguyên tắc nội dung (áp dụng mọi prompt sinh văn bản)

1. **3 tầng:** Observation (số liệu) → Explanation (nguyên nhân, dựa trên dữ liệu) → Action (gợi ý, có điều kiện "nếu bạn muốn...").
2. **Không phán xét:** cấm các cụm như "bạn tiêu quá nhiều", "lãng phí", "bạn phải", "bạn nên ngay lập tức", "kém kỷ luật". Dùng "cao hơn tháng trước X%", "phần lớn mức tăng đến từ...", "bạn có thể cân nhắc...". Review không tự kết luận "ngân sách sai / hành vi sai" — việc đó thuộc Budget advisor (Phase 8).
3. **Không bịa số:** mọi con số trong output phải có trong input metrics. Kiểm tra tự động: trích số từ narrative và đối chiếu với metrics (golden test).
4. **AI không quyết định thay user:** luôn trả draft/gợi ý, user xác nhận.
5. Ngôn ngữ: tiếng Việt, xưng "bạn".

Prompt lưu ở `backend/app/ai/prompts/*.md` (có version trong tên hoặc header), không inline dài trong code. Phase 3: `nl_transaction_parse.v3.md` (placeholder `{{today}}`, `{{calendar}}`, `{{categories}}`, `{{preferences}}`, `{{amount_hints}}`… do `nl_transaction_parser.build_messages` điền; v3 = v2 + mục "Sở thích phân loại của người dùng") và `classification_preference_parse.v1.md`. Phase 6: `review_narrative.v1.md` (`{{period_word}}`, `{{period_label}}`, `{{metrics_json}}`, `{{allowed_numbers}}`). Phase 7: `review_narrative_month.v1.md` (cùng placeholder). Phase 8: `budget_advice_explanation.v1.md` (xem § 4b). Phase 10: `coach_v1.md` (system prompt Financial Coach, xem § 5). Phase 11: `coach_v2.md` = v1 + gợi ý gọi `get_goals`, ý nghĩa `months_remaining` / `suggested_monthly_saving` / `overdue`, link [Mục tiêu](/goals) trong giới hạn chỉ đọc (Phase 11 không có prompt / lời gọi AI mới nào khác).

## 3. Structured output chính (phác thảo)

```python
# Phase 2 — app/schemas/ai.py (output của model; API trả thêm category_id đã resolve)
class TransactionDraftOutput(BaseModel):
    direction: Literal["income", "expense"]
    amount: int                      # đồng, > 0
    occurred_on: date                # model resolve ngày tương đối từ lịch tham chiếu; không nêu = hôm nay
    note: str
    category_slug: str               # phải thuộc danh sách category đang dùng gửi kèm (backend hậu kiểm)
    spending_type: Literal["essential", "non_essential", "irregular"] | None  # income = None, expense bắt buộc
    confidence: float                # 0..1 (UI nhắc kiểm tra khi < 0.6)
    reason: str                      # vì sao chọn category/type

class TransactionParseOutput(BaseModel):
    transactions: list[TransactionDraftOutput]   # 1..10, giữ thứ tự trong câu
    warnings: list[str]
```

Hậu kiểm deterministic sau khi model trả về (Phase 2): slug tồn tại + `kind` khớp `direction` (sai → gửi lỗi cho model sửa 1 lần → vẫn sai thì `502 AI_INVALID_OUTPUT`); `amount` đối chiếu với số tiền trích bằng quy tắc (`services/amount_text.extract_amounts`) → warning nếu lệch hoặc thiếu khoản; ngày ở tương lai / quá 1 năm → warning. Câu không có số tiền bị chặn trước khi gọi AI (`422 amount_missing`).

```python
class ReviewNarrative(BaseModel):
    observation: str                 # What happened?
    explanation: str                 # Why?
    notice: list[str]                # What should you notice? (1-3 ý)
    action: str | None               # gợi ý có điều kiện, không ra lệnh
    reflection_question: str         # câu hỏi cho user
```

## 4. LangGraph — Review graph (Phase 6, 7)

Cùng một graph, tham số `period = week | month`.

```mermaid
stateDiagram-v2
    [*] --> collect_metrics
    collect_metrics: collect_metrics (deterministic)<br/>tổng thu/chi, breakdown spending_type,<br/>so sánh kỳ trước, top giao dịch
    collect_metrics --> detect_highlights
    detect_highlights: detect_highlights (deterministic)<br/>category tăng mạnh nhất, giao dịch lớn,<br/>cụm giao dịch lặp (vd 4 lần ăn tối)
    detect_highlights --> write_narrative
    write_narrative: write_narrative (LLM)<br/>ReviewNarrative structured output
    write_narrative --> validate
    validate: validate (deterministic)<br/>số trong narrative ⊆ metrics,<br/>không chứa cụm từ cấm
    validate --> write_narrative: fail và retry < 2
    validate --> persist: pass
    validate --> fallback: fail và retry = 2
    fallback: fallback_template<br/>narrative dạng template không dùng LLM
    fallback --> persist
    persist --> [*]
```

Triển khai Phase 6 (`app/agents/review_graph.py`, LangGraph 1.2):
- `collect_metrics` → `analytics_service.get_review_metrics(period, start, today)`; `detect_highlights` → `services/review_metrics.detect_highlights` (top 3 danh mục, danh mục tăng/giảm nhiều nhất theo đồng, cụm lặp ≥ 3 khoản cùng danh mục + cùng buổi trong ngày theo từ khoá ghi chú "sáng/trưa/tối/đêm/khuya", hoặc cùng pattern ghi chú đã chuẩn hoá; top 3 khoản chi).
- `write_narrative` → `ai/review_writer` (prompt `review_narrative.v1.md`, model `OPENAI_MODEL_SMART`, timeout 60s); prompt kèm metrics JSON (bỏ UUID) + **danh sách số được phép** định dạng kiểu Việt Nam.
- `validate` → `services/review_narrative.validate_narrative`: trích mọi số trong văn bản ("1.180.000", "18%", "0,5 triệu", "620k", ngày "12/10") và so với tập số có trong metrics (tiền, %, số lượng, ngày/tháng/năm, số trong ghi chú; giá trị tuyệt đối); cụm từ cấm (so khớp cả không dấu); đủ observation/explanation/notice/reflection; có `action` khi tuần có giao dịch và action phải có điều kiện ("nếu", "có thể", "cân nhắc", "thử"). Fail → gửi danh sách lỗi cho model viết lại (retry ≤ 2, tức tối đa 3 lần gọi).
- AI lỗi (`AIUnavailable`: chưa cấu hình, timeout, 5xx…) → **không retry**, sang `fallback` ngay. `fallback_template` dựng narrative từ metrics (luôn qua validate), `fallback_reason` = mã lỗi AI hoặc `validation_failed`.
- `persist` theo `period` (`week` → `review_service.save_weekly_review`, `month` → `save_monthly_review`). Endpoint `POST /reviews/weekly|monthly` không chạy graph nếu kỳ đã có review và `regenerate=false`.

Mở rộng Phase 7 (`period = month`, cùng graph — không có workflow riêng):
- `collect_metrics` gom thêm `analytics_service.get_monthly_budget_summary` (budget vs actual Phase 5, chỉ budget active/closed) và `review_service.weekly_reflections_in_month`; `detect_highlights` gọi `review_metrics.build_review_metrics` → `MonthlyReviewMetrics` (tiết kiệm, tỉ lệ, tỉ trọng spending_type, chi thường xuyên vs bất thường, `increase_driver`, khoản bất thường). `GET /reviews/monthly/{month}/metrics` chạy đúng 2 bước này (không AI, không lưu).
- `review_writer` chọn prompt theo kỳ: `review_narrative_month.v1.md` (bắt buộc nêu khoản bất thường khi `increase_driver = irregular`, chỉ gợi ý "xem tư vấn điều chỉnh ngân sách", không tự kết luận ngân sách/hành vi sai). Metrics gửi model và tập số được phép dùng chung `review_narrative.metrics_payload` (bỏ mọi khoá `id`/`*_id`/`*_ids`/`key`/`icon`).
- `validate` thêm cho tháng: chi tăng chủ yếu do khoản bất thường → observation/explanation phải chứa số tiền khoản bất thường lớn nhất. Cụm cấm thêm (cả tuần): "kém kỷ luật", "thiếu kỷ luật", "thói quen xấu", "ngân sách sai", "đặt sai ngân sách", "ngân sách đặt sai", "ngân sách không/chưa hợp lý", `adjust_budget`, `adjust_behavior`.
- Fallback tháng: thu/chi/còn lại/tỉ lệ tiết kiệm, nguyên nhân (khoản bất thường hoặc danh mục), cơ cấu kèm %, ý đáng chú ý ưu tiên dòng vượt ngân sách → khoản bất thường → khoản đã đánh dấu trong tuần → cụm lặp; câu hỏi "giữ gì / điều chỉnh gì cho tháng tới".

## 4b. Giải thích Budget advice (Phase 8)

Không dùng LangGraph — một lời gọi Structured Outputs cho mỗi advice (`app/ai/advice_writer.py`):

- Input: `verdict` + `evidence` do `services/advisor_rules` tính sẵn (decision tree ở [budget-adjustment.md](./budget-adjustment.md)). Model **không** quyết định verdict.
- Prompt `budget_advice_explanation.v1.md` (`{{verdict}}`, `{{verdict_label}}`, `{{verdict_guide}}` — hướng dẫn riêng từng verdict, `{{evidence_json}}` — evidence bỏ ID, `{{allowed_numbers}}`). Model `OPENAI_MODEL_FAST`, timeout 30s, output `BudgetAdviceExplanation` (`observation`, `explanation`, `action`, `tone`).
- Validate (`services/advice_narrative.validate_explanation`, truyền vào `structured_completion(validate=…)` → sai thì model sửa 1 lần): số ⊆ evidence; cụm phán xét (+ "sai lầm"); cấm tự nhận đã làm ("tôi đã điều chỉnh", "đã cập nhật ngân sách", "app đã"…); verdict ≠ `adjust_budget` cấm gợi ý tăng ngân sách; `adjust_budget` phải nêu `proposed_planned_amount`; `one_off` phải nêu số tiền giao dịch ngoại lệ; action có điều kiện (bắt buộc trừ `on_track`); cấm lộ tên trường / mã kỹ thuật (`cv_pct`, `adjust_budget`).
- Vẫn sai hoặc AI lỗi → `template_explanation` (deterministic, luôn qua validate), `model = fallback_template`, `narrative.fallback_reason` = mã lỗi. Verdict `on_track` luôn dùng template (`model = template`, không gọi AI). Nhiều advice → gọi song song (tối đa 4).
- Golden: `tests/ai_golden/test_budget_advice_explanation.py` (Ăn uống `adjust_budget`, Laptop `one_off`, Giải trí `adjust_behavior`, chống prompt phán xét).

## 5. LangGraph — Financial Coach graph (Phase 10, 16)

```mermaid
stateDiagram-v2
    [*] --> scope_check
    scope_check: scope_check (deterministic)<br/>đầu tư / chứng khoán / crypto / thuế,<br/>yêu cầu ghi dữ liệu
    scope_check --> [*]: từ chối bằng template (không gọi model)
    scope_check --> agent
    agent: agent (LLM + tools bound)
    agent --> tools: có tool_calls
    tools: ToolNode<br/>get_spending_summary, get_budget_status,<br/>get_category_trend, get_budget_advice,<br/>get_recent_reviews, get_goals (P11) · sau này:<br/>search_transactions (P15), search_knowledge (P16), simulate (P17)
    tools --> agent
    agent --> guard: trả lời cuối
    guard: response_guard (deterministic)<br/>số ⊆ output tool, cụm từ cấm,<br/>3 tầng + gợi ý có điều kiện
    guard --> agent: cần sửa (tối đa 1 lần)
    guard --> [*]: ok / fallback từ evidence
```

- Tools **chỉ đọc** (read-only). Coach không tạo/sửa giao dịch hay budget; nếu user muốn, Coach trả về link/gợi ý tới màn hình tương ứng.
- Giới hạn tối đa 6 vòng tool call / câu hỏi.
- Lịch sử chat lưu `chat_sessions` / `chat_messages`.

Triển khai Phase 10 (`app/agents/coach_graph.py`, LangGraph 1.2.16 + `langgraph-prebuilt` 1.1.1 `ToolNode`, `langchain-core` 1.6 `@tool`):
- `agent` gọi `ai/openai_client.chat_with_tools` (Chat Completions function calling, `OPENAI_MODEL_SMART`, timeout 60s, temperature 0) — **không** dùng `langchain-openai`; graph tự chuyển message LangChain ↔ OpenAI. Đủ 6 vòng tool → gọi lần cuối với `tool_choice="none"`. Prompt `prompts/coach_v2.md` (Phase 11; v1 ở Phase 10) (`{{today}}`, `{{weekday}}`, `{{current_month}}`, `{{previous_month}}`), lịch sử = 10 message user/assistant gần nhất của session (không gồm tool output cũ).
- `tools` = `ToolNode` (`wrap_tool_call` ghi tool trace + latency; các lần gọi tuần tự hoá bằng lock vì dùng chung 1 SQLAlchemy Session; lỗi nghiệp vụ / tham số trả về model dạng ToolMessage lỗi). Tool ở `agents/tools/finance_tools.py`, đăng ký qua `CoachToolRegistry` (`agents/tools/registry.py`; tên tool tương lai chưa đăng ký bị bỏ qua). Mỗi tool chỉ gọi `services/insight_service` (số liệu deterministic: tổng thu chi, trend N tháng kết thúc ở tháng đã trọn + độ lệch chuẩn population và hạng biến động, Budget vs Actual + vùng, advice đã có, review gần đây).
- `response_guard` → `services/coach_guard`: số trong câu trả lời ⊆ số trong output tool đã gọi (bỏ ID; gồm khoá `YYYY-MM`) + số trong câu hỏi + ngày hôm nay + 0–12; cụm cấm (review + "ngay lập tức", "bạn cần phải", "tôi/mình đã điều chỉnh…"); tên kỹ thuật `snake_case`; câu trả lời có số tiền phải có "Quan sát", "Vì sao" và gợi ý có điều kiện; khuyến nghị không số liệu cũng phải có điều kiện. Fail → yêu cầu viết lại 1 lần → vẫn fail → `fallback_answer` liệt kê evidence (`guard_status = fallback`).
- `scope_check` → `coach_guard.classify_request` (so khớp có dấu để không nhầm "thuế"/"thuê"): ngoài phạm vi → `refused_out_of_scope`; yêu cầu ghi (động từ ghi + đối tượng + "giúp/hộ/tự…" hoặc câu mở đầu bằng động từ, không có ý hỏi "xem/nên/nào/không…") → `refused_write_request` với link `/budget`, `/budget/advice`, `/transactions`.
- Sau graph: `coach_evidence.select_evidence` giữ dòng evidence (nhãn, kỳ, chỉ số, số tiền) có số tiền được câu trả lời trích → bảng "Dữ liệu đã dùng" + `evidence_refs` của từng tool call. `core/ai_usage` cộng token, ước tính chi phí (giá USD/1M token × 26.000 đ) và log 1 dòng `ai_usage task=coach …`.
- AI lỗi → `AIUnavailable` không bị bắt trong graph: user message đã lưu, router trả 503 (`AI_NOT_CONFIGURED` / `AI_TIMEOUT` / `AI_UNAVAILABLE`…).
- Golden: `tests/ai_golden/test_coach.py` ("Tao nên giảm khoản nào?", "Tháng này khoản nào vượt budget?", chống giọng phán xét, từ chối ngoài phạm vi / yêu cầu ghi).
- Phase 11: tool thứ 6 `get_goals` (không tham số, `finance_tools.goals_tool` → `services/goal_service.get_goals_overview`: goal active theo priority với số tiền mục tiêu / đã có / còn thiếu / % / hạn / số tháng còn lại / gợi ý mỗi tháng / đúng tiến độ, tổng gợi ý mỗi tháng, số goal tạm dừng / đã đạt). Chỉ đọc; "mục tiêu", "khoản góp" thêm vào đối tượng ghi của `scope_check` (từ chối kèm link `/goals`). Evidence: Số tiền mục tiêu / Đã có / Còn thiếu / Nên để dành / tháng. Prompt `coach_v2.md`; golden thêm câu hỏi mục tiêu laptop (trích 4.400.000) và từ chối "Thêm 2 triệu vào mục tiêu laptop giúp tao".

## 6. Classification memory (Phase 3)

```mermaid
flowchart LR
    inp["Câu nhập mới"] --> norm["Chuẩn hoá<br/>lowercase, bỏ dấu, bỏ số tiền"]
    norm --> match["Tìm preference khớp<br/>(keyword overlap; P15: + vector similarity)"]
    match -->|"khớp mạnh (exact pattern)<br/>+ câu đơn giản"| direct["Draft deterministic<br/>(không gọi LLM)"]
    match -->|"khớp một phần"| fewshot["Đưa top-5 preference<br/>vào prompt làm few-shot"]
    match -->|"không khớp"| plain["Prompt thường"]
    fewshot --> llm["LLM parse + classify"]
    plain --> llm
    llm --> post["Hậu kiểm: draft nào exact-match<br/>→ phân loại theo preference"]
    direct --> draft["Draft cho user"]
    post --> draft
    draft --> confirm{"User sửa?"}
    confirm -->|"Có"| save["Lưu feedback +<br/>upsert preference"]
    confirm -->|"Không, draft dùng preference"| hit["Tăng hit_count"]
```

Chi tiết triển khai:
- **Chuẩn hoá** (`services/classification_text`, deterministic): `"Mua giày MLB 1.8 triệu"` → `mua giay mlb`. Pattern lưu bỏ thêm từ chung (`STOPWORDS`: động từ chung, đại từ, lượng từ, từ chỉ thời gian). Keyword học từ correction = từ có nghĩa đầu tiên của ghi chú (+ từ ngay sau nếu là "từ đầu" như `tien`, `sua`, `phi`…): `giay`, `sua laptop`, `tien nha`.
- **Exact match**: mọi token của pattern có trong câu (không cần liền nhau — `sua laptop` khớp "sửa màn hình laptop"); pattern chỉ gồm từ chung (`mua`, `tien`) bị coi là quá rộng, không áp dụng. Nhiều preference khớp → pattern nhiều token nhất, rồi `hit_count`, rồi mới dùng gần nhất. Preference của danh mục đã ẩn bị bỏ qua.
- **Shortcut không gọi OpenAI** chỉ khi câu đơn giản: đúng 1 khoản tiền, không còn chữ số khác, không có từ chỉ ngày (`qua`, `thu`, `tuan`, `t7`…), và không có từ gợi ý chiều tiền ngược với danh mục của preference (`ban`, `nhan`… với preference chi tiêu). Draft: `amount` từ `extract_amounts`, `occurred_on` = hôm nay, `confidence = 0.95`, `reason = "Theo sở thích phân loại đã học: “giay” → Mua sắm · Thiết yếu"`, `matched_preference_id`, response `model = "classification_preference"`. Câu còn lại đi LLM (few-shot = preference có token chung), sau đó từng draft exact-match (theo ghi chú của draft; câu 1 draft dùng thêm token câu gốc, cùng `direction`) bị ghi đè phân loại theo preference.
- **Parse không ghi DB** (kể cả `hit_count`); học/tăng `hit_count` xảy ra trong `POST /transactions` (cùng commit) dựa trên `ai_suggestion` mà frontend gửi kèm. Response `POST /transactions` có `learned_preference` khi vừa học.
- **Explicit preference**: `POST /classification-preferences/parse` (LLM → `PreferenceDraft`, hậu kiểm slug/kind/pattern đủ cụ thể, sai → model sửa 1 lần → 502) → user sửa/xác nhận → `POST /classification-preferences` (upsert theo pattern).

## 7. Đánh giá chất lượng AI (golden tests)

- Thư mục `backend/tests/ai_golden/` chứa file YAML/JSON test cases cố định cho từng tác vụ.
- Chạy: `pytest -m ai` (cần `OPENAI_API_KEY`); mặc định CI/local `pytest` bỏ qua.
- Mỗi phase AI định nghĩa ngưỡng pass (ví dụ NL parse: amount đúng 100%, direction đúng 100%, category đúng >= 80%).
- Khi sửa prompt: chạy lại golden test, ghi kết quả vào Handoff notes của phase.
