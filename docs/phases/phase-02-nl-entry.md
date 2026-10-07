# Phase 02 — Natural Language Transaction Entry

| | |
|---|---|
| **ID** | `phase-02-nl-entry` |
| **Trạng thái** | Not started |
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

- [ ] T1 Hoàn thiện `ai/openai_client.py` với cấu hình env, timeout, retry/backoff, Pydantic validation, lỗi `AIUnavailable`
- [ ] T2 Thêm schema `TransactionDraft` / parse request-response và unit test validate amount/direction/spending_type
- [ ] T3 Implement `nl_transaction_parser.parse_transactions()` nhận text, today, categories; hậu kiểm slug/ngày
- [ ] T4 Thêm `POST /api/v1/transactions/parse` + test 503 khi thiếu key bằng mock `is_configured=false`
- [ ] T5 Bảo đảm `POST /transactions` lưu được `source='nl'`, `raw_input`, `ai_suggestion` khi user xác nhận
- [ ] T6 Thêm golden test file cho ≥10 câu tiếng Việt, mark `@pytest.mark.ai`, threshold rõ ràng
- [ ] T7 Thêm mock-based API tests không cần OpenAI key cho one draft, multi draft, invalid category từ AI
- [ ] T8 UI `QuickAddBox` trên `/` gọi parse và hiển thị lỗi/loading
- [ ] T9 UI `TransactionDraftReview` cho sửa/lưu/bỏ qua từng draft; tái dùng form controls Phase 1
- [ ] T10 Chạy sinh lại OpenAPI types nếu schema thay đổi
- [ ] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-02: natural language entry`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
cd backend
alembic upgrade head
ruff check .
pytest
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL_FAST="gpt-4o-mini"
pytest -m ai
uvicorn app.main:app --reload --port 8000

cd ..\frontend
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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` không cần API key vẫn xanh; AI golden chỉ chạy khi `pytest -m ai`
- [ ] `ruff check`, `npm run lint`, `npm run gen:api` xanh
- [ ] Không có endpoint AI nào tự ghi DB
- [ ] `raw_input` và `ai_suggestion` được lưu khi user xác nhận draft
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done
- [ ] Mục 9 Handoff notes đã điền
- [ ] Commit với message `phase-02: natural language entry`

## 8. Rủi ro / câu hỏi mở

- "thứ 7 tuần trước" phụ thuộc định nghĩa tuần bắt đầu Thứ Hai; dùng helper Phase 1 và ghi rõ trong test.
- Câu thiếu amount ("ăn phở") nên trả warning/422 thay vì đoán tiền.
- Category `food` có thể là essential hoặc non_essential tuỳ ngữ cảnh (ăn trưa vs cafe); Phase 3 sẽ học preference, Phase 2 chấp nhận sai có thể sửa.
- Nếu Phase 1 chưa tạo `raw_input`/`ai_suggestion` thì cần migration bổ sung dù plan mong đã có.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
