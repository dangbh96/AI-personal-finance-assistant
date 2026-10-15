# Phase 02 — Natural Language Transaction Entry

| | |
|---|---|
| **ID** | `phase-02-nl-entry` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 1 |
| **Mở khoá** | Phase 3, 13 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 1](./phase-01-transactions.md)
2. [glossary.md](../product/glossary.md) — viết tắt tiền (`55k`, `1tr5`, `2 lít`), `direction`, `spending_type`, category slug
3. [vision.md](../product/vision.md) — human-in-the-loop, không phán xét, AI chỉ tạo draft
4. [data-model.md](../architecture/data-model.md) — `transactions.raw_input`, `transactions.ai_suggestion`, money `BIGINT`
5. [backend-components.md](../architecture/backend-components.md) — `ai/openai_client`, router trả draft, không ghi DB trực tiếp
6. [ai-architecture.md](../architecture/ai-architecture.md) — structured outputs, model env, golden tests
7. [sequences.md](../architecture/sequences.md) — sequence "Nhập giao dịch bằng câu tự nhiên"
8. [frontend-structure.md](../architecture/frontend-structure.md) — route `/` có Quick add, `/transactions` xác nhận draft
9. ADR [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu: Phase 1 Done; có `categories`, `transactions` với cột `raw_input`, `ai_suggestion`, `source`; CRUD transaction hoạt động; `ai/openai_client.py` mới có khung cấu hình.

## 2. Mục tiêu & giá trị cho user

User nhập giao dịch bằng tiếng Việt tự nhiên như "Hôm nay ăn phở 55k" hoặc "Tháng này nhận lương 25 triệu". AI chuyển thành một hoặc nhiều draft có cấu trúc để user xác nhận/sửa rồi mới lưu, giảm ma sát ghi chép hằng ngày nhưng vẫn giữ quyền kiểm soát dữ liệu.

## 3. Scope

**In scope**
- `POST /api/v1/transactions/parse` gọi OpenAI structured output, trả về `list[TransactionDraft]` **chưa lưu DB**; kể cả một giao dịch cũng trả list 1 phần tử để thống nhất với câu có nhiều giao dịch.
- Hiểu slang tiền trong glossary: `55k`, `45 nghìn`, `1tr5`, `1.5tr`, `25 triệu`, `2 lít`, `1 củ`; mọi amount trả về là số nguyên VND.
- Resolve ngày tương đối (`hôm nay`, `hôm qua`, `thứ 7 tuần trước`, `tháng này`) bằng `today` do frontend/backend truyền vào prompt; nếu không rõ ngày thì default hôm nay.
- Nhận diện nhiều giao dịch trong một câu: "sáng cafe 35k, trưa phở 55k, tối Grab 90k" → 3 draft.
- `ai/openai_client` có timeout, retry/backoff, validate Pydantic, retry khi structured output lỗi; router trả 503 thân thiện khi thiếu key/lỗi AI.
- UI Quick add trên `/`, draft confirmation UI, sau khi user bấm Lưu gọi CRUD Phase 1 và lưu `raw_input`, `ai_suggestion`, `source='nl'`.
- Golden tests `@pytest.mark.ai` cho ≥10 câu tiếng Việt.

**Out of scope**
- Học preference từ correction (Phase 3); phase này chỉ lưu `ai_suggestion` để Phase 3 dùng.
- OCR hoá đơn (Phase 13), import CSV (Phase 14), recurring detection (Phase 12).
- Tự động lưu không cần xác nhận; không parse đầu tư/đa tiền tệ.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Không tạo bảng mới nếu Phase 1 đã tạo đúng:
- `transactions.raw_input TEXT NULL`: câu gốc user nhập.
- `transactions.ai_suggestion JSONB NULL`: toàn bộ draft AI trả về tại thời điểm xác nhận.
- `transactions.source TEXT DEFAULT 'manual'`: Phase 2 dùng `nl`.

Nếu Phase 1 chưa có các cột này thì tạo migration bổ sung, nhưng không đổi schema khác. Service tạo transaction phải cho phép `source='nl'` và validate như manual: category slug tồn tại, kind khớp `direction`, expense bắt buộc có `spending_type`, amount > 0.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| POST | `/api/v1/transactions/parse` | Parse câu tự nhiên thành draft, không lưu DB | `{ "text": "Hôm nay ăn phở 55k", "today": "2026-10-07", "timezone": "Asia/Ho_Chi_Minh" }` | `200 { "drafts": [TransactionDraft], "model": "gpt-4o-mini", "raw_input": "...", "warnings": [] }` |
| POST | `/api/v1/transactions` | Có sẵn Phase 1; Phase 2 dùng để lưu draft đã xác nhận | `TransactionCreate` + `raw_input`, `ai_suggestion`, `source="nl"` | `201 TransactionRead` |

Module chính:
- `app/ai/openai_client.py`: `is_configured()`, `structured_completion(schema, messages, model, timeout=20)`, retry tối đa 2 lần cho network/429/5xx; validate Pydantic; nếu validate fail thì retry 1 lần với lỗi schema; raise `AIUnavailable(code, message)`.
- `app/ai/nl_transaction_parser.py`: lấy active categories từ service, build prompt, gọi `openai_client`, hậu kiểm category slug và ngày.
- `app/schemas/ai.py`: `TransactionDraft`, `TransactionParseRequest`, `TransactionParseResponse`.
- `app/api/routers/transactions.py`: thêm route `/parse` đặt trước `/{id}`.

### 4.3 AI

Model đọc từ env:
- `OPENAI_MODEL_FAST` cho parse/classify nhanh, default `gpt-4o-mini`.
- `OPENAI_MODEL_SMART` chưa dùng ở phase này.

Structured output:
```python
class TransactionDraft(BaseModel):
    direction: Literal["income", "expense"]
    amount: int = Field(gt=0, description="VND, integer dong")
    occurred_on: date
    note: str
    category_slug: str
    spending_type: Literal["essential", "non_essential", "irregular"] | None
    confidence: float = Field(ge=0, le=1)
    reason: str

class TransactionParseOutput(BaseModel):
    transactions: list[TransactionDraft] = Field(min_length=1, max_length=10)
    warnings: list[str] = []
```

Prompt outline:
1. System: "Bạn là parser giao dịch tài chính cá nhân, chỉ trả JSON theo schema, không lưu dữ liệu."
2. Quy tắc tiền: liệt kê slang từ glossary; không dùng float; `amount` là đồng.
3. Quy tắc ngày: `today={today}`, timezone Asia/Ho_Chi_Minh; resolve ngày tương đối; nếu không có ngày dùng today.
4. Quy tắc phân loại: chỉ chọn `category_slug` trong danh sách categories gửi kèm; income có `spending_type=null`; expense có một trong 3 type.
5. Quy tắc nhiều giao dịch: tách theo ý nghĩa, mỗi khoản tiền là một draft riêng nếu có note/category riêng.

Guardrails:
- Không bịa category ngoài danh sách; backend reject nếu slug không hợp lệ.
- Nếu câu mơ hồ nhưng có amount, trả draft confidence thấp + warning; UI bắt user kiểm tra.
- Không log API key; không log full prompt nếu chứa dữ liệu nhạy cảm trong production.
- Không tự ghi DB; mọi draft phải qua user xác nhận.

### 4.4 Frontend

- `/`: thêm `QuickAddBox` gồm textarea một dòng, nút "Phân tích", trạng thái loading/error.
- `TransactionDraftReview`: card cho từng draft; user sửa amount/date/category/spending_type/note trước khi lưu.
- Với nhiều draft: nút "Lưu tất cả" và từng nút "Bỏ qua"; nếu một draft lỗi validate thì không chặn draft khác đã sửa hợp lệ.
- Sau khi lưu thành công: clear input, toast "Đã lưu 3 giao dịch", refresh month summary/transaction list nếu đang có.
- Khi backend trả 503 do chưa có `OPENAI_API_KEY`: hiển thị "Chưa cấu hình AI. Bạn vẫn có thể nhập thủ công ở /transactions." kèm link.

## 5. Task breakdown

- [x] T1 Hoàn thiện `ai/openai_client.py` với cấu hình env, timeout, retry/backoff, Pydantic validation, lỗi `AIUnavailable`
- [x] T2 Thêm schema `TransactionDraft` / parse request-response và unit test validate amount/direction/spending_type
- [x] T3 Implement `nl_transaction_parser.parse_transactions()` nhận text, today, categories; hậu kiểm slug/ngày
- [x] T4 Thêm `POST /api/v1/transactions/parse` + test 503 khi thiếu key bằng mock `is_configured=false`
- [x] T5 Bảo đảm `POST /transactions` lưu được `source='nl'`, `raw_input`, `ai_suggestion` khi user xác nhận
- [x] T6 Thêm golden test file cho ≥10 câu tiếng Việt, mark `@pytest.mark.ai`, threshold rõ ràng (12 câu; kết quả ở § 9)
- [x] T7 Thêm mock-based API tests không cần OpenAI key cho one draft, multi draft, invalid category từ AI
- [x] T8 UI `QuickAddBox` trên `/` gọi parse và hiển thị lỗi/loading
- [x] T9 UI `TransactionDraftReview` cho sửa/lưu/bỏ qua từng draft; tái dùng form controls Phase 1
- [x] T10 Chạy sinh lại OpenAPI types nếu schema thay đổi
- [x] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-02: natural language entry`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL_FAST="gpt-4o-mini"
pytest -m ai
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest, không cần API key bằng mock)**
| # | Input | Kỳ vọng |
|---|---|---|
| 1 | parse `"Hôm nay ăn phở 55k"`, today `2026-10-07` | 200, 1 draft amount `55000`, direction `expense`, occurred_on `2026-10-07` |
| 2 | parse mock trả category slug `unknown` | 422 hoặc 502 có `code="AI_INVALID_OUTPUT"` |
| 3 | không có `OPENAI_API_KEY` | 503 `code="AI_NOT_CONFIGURED"`, không crash |
| 4 | save draft phở với `raw_input` | transaction `source="nl"`, `raw_input` giữ nguyên, `ai_suggestion` có JSON draft |
| 5 | parse `"sáng cafe 35k, trưa cơm 60k"` | response có 2 draft, tổng amount không tự cộng |
| 6 | AI trả income với spending_type `essential` | validation fail và retry; sau retry vẫn sai → lỗi rõ ràng |

**Golden set (`pytest -m ai`)**
| # | Input | today | Expected amount | direction | category_slug | spending_type |
|---|---|---|---:|---|---|---|
| 1 | Hôm nay ăn phở 55k | 2026-10-07 | 55000 | expense | food | essential |
| 2 | Grab về nhà 45 nghìn | 2026-10-07 | 45000 | expense | transport | essential |
| 3 | Tháng này nhận lương 25 triệu | 2026-10-07 | 25000000 | income | salary | null |
| 4 | Mua tai nghe 1tr5 | 2026-10-07 | 1500000 | expense | electronics | non_essential |
| 5 | cafe 2 lít | 2026-10-07 | 200000 | expense | food | non_essential |
| 6 | Hôm qua đóng tiền điện 780k | 2026-10-07 | 780000 | expense | utilities | essential |
| 7 | Thứ 7 tuần trước đi khám 650 nghìn | 2026-10-07 | 650000 | expense | health | essential |
| 8 | Được thưởng dự án 3 củ | 2026-10-07 | 3000000 | income | bonus | null |
| 9 | Mua áo sơ mi 450k | 2026-10-07 | 450000 | expense | shopping | non_essential |
| 10 | Sửa laptop 1.2tr | 2026-10-07 | 1200000 | expense | electronics | irregular |
| 11 | Sáng cafe 35k, trưa phở 55k, tối Grab 90k | 2026-10-07 | 3 drafts: 35000/55000/90000 | expense | food/food/transport | non_essential/essential/essential |
| 12 | Nhận freelance 4 triệu rưỡi | 2026-10-07 | 4500000 | income | freelance | null |

Pass threshold: amount đúng 100%, direction đúng 100%, occurred_on đúng ≥90%, category_slug đúng ≥80%, spending_type đúng ≥80%, multi-transaction count đúng 100%.

**Kịch bản thao tác UI**
1. Mở `/`, nhập "Hôm nay ăn phở 55k" → thấy draft 55.000 ₫, Ăn uống, Thiết yếu, hôm nay.
2. Sửa note thành "Phở bò", bấm Lưu → transaction xuất hiện trong `/transactions`, source là NL.
3. Nhập "sáng cafe 35k, trưa cơm 60k" → thấy 2 card draft; bỏ qua cafe, lưu cơm.
4. Xoá `OPENAI_API_KEY`, reload → Quick add báo AI chưa cấu hình và link nhập thủ công.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass (golden set đạt 100% mọi chỉ số, 3/3 lần chạy)
- [x] `pytest` không cần API key vẫn xanh; AI golden chỉ chạy khi `pytest -m ai`
- [x] `ruff check`, `npm run lint`, `npm run gen:api` xanh
- [x] Không có endpoint AI nào tự ghi DB
- [x] `raw_input` và `ai_suggestion` được lưu khi user xác nhận draft
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done
- [x] Mục 9 Handoff notes đã điền
- [x] Commit với message `phase-02: natural language entry`

## 8. Rủi ro / câu hỏi mở

- "thứ 7 tuần trước" phụ thuộc định nghĩa tuần bắt đầu Thứ Hai; dùng helper Phase 1 và ghi rõ trong test.
- Câu thiếu amount ("ăn phở") nên trả warning/422 thay vì đoán tiền.
- Category `food` có thể là essential hoặc non_essential tuỳ ngữ cảnh (ăn trưa vs cafe); Phase 3 sẽ học preference, Phase 2 chấp nhận sai có thể sửa.
- Nếu Phase 1 chưa tạo `raw_input`/`ai_suggestion` thì cần migration bổ sung dù plan mong đã có.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-13
- **Đã làm:**
  - **`ai/openai_client.py`:** `is_configured`/`ensure_configured`, `structured_completion(schema, messages, *, task, model, timeout=20, validate)` → `(output, model)`. Chat Completions `response_format=json_schema` strict (sinh từ Pydantic bằng `to_strict_json_schema`, bỏ `minLength`/`maxLength`/`default`), `temperature=0`. Retry mạng/429/5xx do SDK (`max_retries=2`, backoff); output sai Pydantic hoặc sai nghiệp vụ (`OutputValidationError` từ callback `validate`) → gửi lỗi cho model sửa **1 lần** → vẫn sai `502 AI_INVALID_OUTPUT`. Lỗi OpenAI map sang `AIUnavailable` (kế thừa `DomainError`): `AI_NOT_CONFIGURED`, `AI_AUTH_FAILED`, `AI_RATE_LIMITED`, `AI_TIMEOUT`, `AI_UNAVAILABLE` (503). Log task/model/token/latency, không log key/prompt.
  - **`schemas/ai.py`:** `TransactionDraftOutput` + `TransactionParseOutput` (output model), `TransactionDraft` (= output + `category_id`), `TransactionParseRequest` (`text` 1..500, `today` tuỳ chọn, `timezone` IANA mặc định `Asia/Ho_Chi_Minh`), `TransactionParseResponse`.
  - **`ai/nl_transaction_parser.py` + `ai/prompts/nl_transaction_parse.v2.md`:** prompt kèm bảng danh mục **đang dùng** (bỏ danh mục đã ẩn), **lịch tham chiếu tính sẵn** (hôm nay/hôm qua/hôm kia; tuần này & tuần trước mỗi ngày một dòng dạng `thứ 7 (Thứ Bảy) tuần trước: 2026-10-03` — tuần từ Thứ Hai qua `services/money.week_range`; tháng này/trước) và số tiền trích bằng quy tắc. Hậu kiểm slug + kind; cảnh báo deterministic: amount không thấy trong câu, số draft < số khoản tiền, ngày tương lai / > 1 năm. Câu không có chữ số / từ chỉ tiền → `422 amount_missing` **trước khi gọi AI**.
  - **`services/amount_text.py`** (deterministic, không AI): `extract_amounts(text)` hiểu `55k`, `45 nghìn`, `1tr5`, `1.5tr`, `1,5 triệu`, `4 triệu rưỡi`, `1tr250`, `2 lít`, `3 củ`, `1 tỷ`, `55.000đ`…; bỏ qua "thứ 7", "2 ly", "năm 2026", ngày/giờ; chỉ dùng số nguyên.
  - **API:** `POST /api/v1/transactions/parse` (không ghi DB). Lưu draft qua `POST /transactions` sẵn có với `source="nl"`, `raw_input`, `ai_suggestion` — không cần đổi schema/migration.
  - **Test (171 pass, 1 deselected):** `tests/unit/test_amount_text.py`, `test_ai_schemas.py`, `test_openai_client.py` (retry/feedback, refusal, map lỗi OpenAI, strict schema), `tests/api/test_transactions_parse.py` (đủ 6 test case mục 6 + archived category, kind mismatch, warnings, default today, không ghi DB). Mock tại seam `openai_client._chat_json` nên đi qua toàn bộ luồng validate thật. Golden: `tests/ai_golden/nl_parse_cases.json` (12 câu mục 6) + `test_nl_parse_golden.py` (in báo cáo từng chỉ số, assert theo ngưỡng; tự skip khi chưa cấu hình key).
  - **Frontend:** tách `components/transactions/transaction-fields.tsx` (`TransactionFields`, `validateTransactionValues`) — dialog Phase 1 và card draft dùng chung. `components/quick-add/quick-add-box.tsx` (trên `/`; gửi `today` + timezone trình duyệt; đọc `/health` để báo sớm "Chưa cấu hình AI" + link `/transactions`) và `transaction-draft-review.tsx` (mỗi draft là form sửa được, badge độ tin cậy, cảnh báo khi `confidence < 0.6`, hiển thị `reason`/`warnings`, Lưu/Bỏ qua từng cái, "Lưu tất cả" tuần tự; draft lỗi không chặn draft khác). Bảng giao dịch có badge nguồn (✨ "Câu tự nhiên"), tooltip hiện câu gốc. `gen:api` đã chạy lại.
  - **Verify:** `ruff check`, `ruff format --check`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 4 kịch bản UI mục 6 đã chạy trên trình duyệt: kịch bản 1–3 với OpenAI thật (draft phở 55.000 ₫ / Ăn uống / Thiết yếu / hôm nay; sửa note "Phở bò" → lưu `source=nl`, `raw_input`, `ai_suggestion` đúng; 2 draft cafe/cơm → bỏ qua cafe, lưu cơm), kịch bản 4 với backend không có key. Đã kiểm tra lại dialog thêm/sửa của Phase 1 sau refactor. Dữ liệu thử đã xoá khỏi DB dev.
  - **Golden set (`pytest -m ai`, `gpt-4o-mini`, 2026-10-15):**

    | Prompt | count | amount | direction | occurred_on | category_slug | spending_type |
    |---|---|---|---|---|---|---|
    | v1 | 12/12 | 14/14 | 14/14 | 13/14 (93%) | 12/14 (86%) | 14/14 |
    | **v2** (3 lần chạy, cả 3 như nhau) | 12/12 | 14/14 | 14/14 | **14/14** | **14/14** | 14/14 |

    v1 đạt ngưỡng nhưng sai có hệ thống: "cafe" → `other` (2 lần) và "thứ 7 tuần trước" → 2026-10-01 (thứ 5) thay vì 2026-10-03. v2: lịch mỗi ngày một dòng, số thứ đặt trước ("thứ 7 (Thứ Bảy) tuần trước: …"), quy tắc tra "thứ N tuần trước", và nói rõ đồ uống thuộc danh mục ăn uống. Chi phí ~2.300 prompt token / câu.
- **Lệch so với plan (và lý do):**
  - Golden test chạy muộn hơn phase (2026-10-15) vì lúc đầu key bị 401; kết quả ở trên. Prompt nâng lên **v2** sau lần chạy đầu.
  - `TransactionDraft` trả thêm `category_id` (frontend cần để POST); `occurred_on` luôn có giá trị (backend đưa lịch tham chiếu nên model luôn resolve được), khác phác thảo `date | None` cũ trong ai-architecture (đã cập nhật).
  - Mã lỗi AI viết HOA theo plan (`AI_NOT_CONFIGURED`…), khác quy ước snake_case thường của lỗi nghiệp vụ Phase 1 (`category_not_found`). Thêm các mã `AI_AUTH_FAILED`, `AI_RATE_LIMITED`, `AI_TIMEOUT`, `AI_UNAVAILABLE`; output sai → **502**.
  - Thêm `services/amount_text.py` + lịch tham chiếu trong prompt (không có trong plan) để giảm sai số tiền/ngày và có cảnh báo deterministic thay vì tin hoàn toàn vào model (ADR-005).
  - Thêm `422 amount_missing` cho câu không có số tiền (mục 8 gợi ý).
  - Thông báo sau khi lưu là dòng trạng thái inline ("Đã lưu N giao dịch" + link), không dùng toast — repo chưa có thư viện toast; trang `/` chưa có summary tháng để refresh (Phase 5).
  - `pyproject.toml`: thêm `package-data` cho `app/ai/prompts/*.md`.
- **Nợ kỹ thuật / TODO để lại:**
  - Ghi chú (`note`) đôi khi giữ từ chỉ thời gian dù prompt dặn bỏ ("Sáng cafe", "Trưa cơm") — không ảnh hưởng số liệu, user sửa được; có thể thêm vào golden set và chỉnh ở prompt v3 nếu cần.
  - Golden set mới có 12 câu, toàn câu "đẹp"; Phase 3 nên bổ sung câu mơ hồ / sai chính tả / không dấu.
  - Retry vòng sửa output gửi lại toàn bộ prompt (token x2 khi model sai) — chấp nhận được với `gpt-4o-mini`.
  - Số tiền viết bằng chữ ("năm mươi nghìn") không trích được bằng quy tắc → không có cảnh báo amount cho các câu này.
  - "2 lít xăng" (lít thật) bị `extract_amounts` hiểu là 200.000 — chỉ ảnh hưởng gợi ý/cảnh báo, không ảnh hưởng draft.
  - Chưa có test tự động cho frontend (QuickAdd/DraftReview) — Vitest/Playwright ở Phase 18.
  - Khi test UI bằng công cụ trình duyệt: tab ở trạng thái `hidden` làm `requestAnimationFrame` dừng → Suspense của `/transactions` kẹt ở "Đang tải…" và Playwright chờ "stable" mãi; không phải bug của app (tab hiển thị load bình thường). Dùng `click(..., { force: true })` hoặc tab mới.
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/api/test_transactions_parse.py -q)`
  - `(cd backend && pytest -m ai -s)` — golden set, in bảng chỉ số (trên console Windows nếu tiếng Việt bị lỗi hiển thị: `export PYTHONIOENCODING=utf-8`)
  - `curl -s -X POST localhost:8000/api/v1/transactions/parse -H 'Content-Type: application/json' -d '{"text":"sáng cafe 35k, trưa phở 55k","today":"2026-10-07"}'`
- **Gợi ý cho phase tiếp theo (Phase 3 — Classification learning):**
  - So sánh `transactions.ai_suggestion` (draft gốc: `category_slug`, `spending_type`, `note`, `model`) với giá trị đã lưu để biết user có sửa không → lưu feedback/upsert preference trong `POST /transactions` khi `source="nl"`.
  - Chèn few-shot preference vào prompt: thêm placeholder mới trong `nl_transaction_parse.v2.md` và tham số cho `build_messages`; giữ `validate` callback để hậu kiểm.
  - Chuẩn hoá câu để match preference: `core/text.strip_accents` + bỏ số tiền (có thể tái dùng regex của `services/amount_text`).
