# Phase 03 — Classification Learning

| | |
|---|---|
| **ID** | `phase-03-classification-learning` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 2 |
| **Mở khoá** | Phase 14 |
| **Milestone** | **M2 — Tracking loop hoàn chỉnh** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 2](./phase-02-nl-entry.md)
2. [glossary.md](../product/glossary.md) — `ClassificationPreference`, `spending_type`, category slug
3. [vision.md](../product/vision.md) — AI học cách user phân loại, không áp đặt
4. [data-model.md](../architecture/data-model.md) — `classification_preferences`, `classification_feedback`
5. [backend-components.md](../architecture/backend-components.md) — AI layer không ghi DB trực tiếp; service/repository chịu trách nhiệm persistence
6. [ai-architecture.md](../architecture/ai-architecture.md) — Classification memory flow, top-5 few-shot, guardrails
7. [sequences.md](../architecture/sequences.md) — user sửa phân loại → lưu preference
8. [frontend-structure.md](../architecture/frontend-structure.md) — `/settings` quản lý preferences
9. ADR [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu: Phase 2 Done; parse NL trả draft và lưu được `raw_input`/`ai_suggestion`; user có thể sửa category/spending_type trước khi lưu transaction.

## 2. Mục tiêu & giá trị cho user

AI nhớ cách user phân loại sau khi user sửa. Ví dụ user sửa "Mua giày MLB 1.8 triệu" thành `essential`; lần sau "Mua giày Nike 2tr" được đề xuất `essential` thay vì mặc định `non_essential`. Tracking loop hoàn chỉnh hơn vì càng dùng càng ít phải sửa.

## 3. Scope

**In scope**
- Tạo bảng `classification_preferences` và `classification_feedback`.
- Chuẩn hoá pattern: lowercase, strip dấu tiếng Việt, bỏ amount/slang tiền, bỏ stopwords ngắn; ví dụ `"Mua giày MLB 1.8 triệu"` → `mua giay mlb` và keyword chính `giay`.
- Exact-match shortcut: nếu normalized input chứa exact pattern preference mạnh → dùng luôn preference, không gọi LLM cho phần phân loại.
- Few-shot top-5: nếu không exact, đưa tối đa 5 preference liên quan vào prompt Phase 2.
- Lưu feedback khi user xác nhận transaction có sửa category/type khác với `ai_suggestion`.
- Upsert preference khi correction lặp lại hoặc explicit preference.
- `/settings` UI xem/xoá preference đã học.
- Hỗ trợ câu explicit preference như "Tao coi giày là thiết yếu" qua endpoint draft riêng, user xác nhận mới lưu.

**Out of scope**
- Vector similarity/embedding preference (Phase 15).
- Batch classify CSV/Excel (Phase 14) — phase này chỉ chuẩn bị service dùng lại.
- Tự động học từ mọi giao dịch user nhập tay không có AI suggestion; chỉ học khi có correction hoặc explicit preference.
- Multi-user preference isolation ngoài `user_id NULL` dự phòng.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`classification_preferences`:
- `id UUID PK`, `user_id UUID NULL`
- `pattern TEXT NOT NULL` — pattern đã chuẩn hoá, ví dụ `giay`
- `example_text TEXT NOT NULL` — câu gốc gần nhất
- `category_id UUID FK categories(id) NOT NULL`
- `spending_type TEXT NULL` — null nếu category income
- `hit_count INT NOT NULL DEFAULT 0`
- `last_used_at TIMESTAMPTZ NULL`, `created_at`, `updated_at`
- Unique đề xuất: `(user_id, pattern, category_id, spending_type)`; với single-user có thể unique expression xử lý `user_id NULL` hoặc service upsert thủ công.
- Index: `pattern`, `last_used_at DESC`.

`classification_feedback`:
- `id UUID PK`, `user_id UUID NULL`
- `transaction_id UUID FK transactions(id) ON DELETE CASCADE`
- `ai_category_id UUID NULL`, `ai_spending_type TEXT NULL`
- `final_category_id UUID FK categories(id)`, `final_spending_type TEXT NULL`
- `created_at`, `updated_at`

Ràng buộc: `final_spending_type IS NULL` nếu final category income; expense phải có type. Tên bảng thực tế dùng số nhiều snake_case.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/classification-preferences` | Danh sách preference đã học | `?q=&category_id=&limit=100` | `{ "items": [PreferenceRead] }` |
| POST | `/api/v1/classification-preferences` | Tạo/upsert explicit preference đã xác nhận | `{ "pattern": "giay", "category_slug": "shopping", "spending_type": "essential", "example_text": "Tao coi giày là thiết yếu" }` | `201 PreferenceRead` |
| DELETE | `/api/v1/classification-preferences/{id}` | Xoá preference | — | `204` |
| POST | `/api/v1/classification-preferences/parse` | Parse câu explicit preference thành draft, không lưu | `{ "text": "Tao coi giày là thiết yếu" }` | `{ "pattern": "giay", "category_slug": "shopping", "spending_type": "essential", "confidence": 0.86 }` |
| POST | `/api/v1/transactions` | Mở rộng Phase 1: nếu payload có `ai_suggestion` và user sửa → lưu feedback/upsert preference | `TransactionCreate` | `201 TransactionRead` |
| POST | `/api/v1/transactions/parse` | Mở rộng Phase 2: exact preference hoặc top-5 few-shot | như Phase 2 | draft được ảnh hưởng bởi preference |

Module:
- `services/classification_preference_service.py`: normalize, find exact, find top-5, upsert, delete, record_feedback.
- `ai/classifier.py`: nhận categories + preferences; nếu exact thì tạo `ClassificationSuggestion` deterministic; nếu không gọi LLM.
- `repositories/classification_preferences.py` và `classification_feedback.py`.
- `services/transaction_service.py`: sau khi create transaction, so sánh `ai_suggestion.category_slug/spending_type` với final; nếu khác thì gọi `record_feedback`.

### 4.3 AI

Model:
- `OPENAI_MODEL_FAST` cho explicit preference parser và fallback classify.
- Không dùng `OPENAI_MODEL_SMART` trong phase này.

Structured output cho classification:
```python
class ClassificationSuggestion(BaseModel):
    category_slug: str
    spending_type: Literal["essential", "non_essential", "irregular"] | None
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_preference_id: UUID | None = None

class PreferenceDraft(BaseModel):
    pattern: str
    category_slug: str
    spending_type: Literal["essential", "non_essential", "irregular"] | None
    confidence: float = Field(ge=0, le=1)
    reason: str
```

Prompt outline:
1. Gửi câu user, amount/date đã parse (nếu có), danh sách categories.
2. Gửi `top_preferences` dạng few-shot: pattern, example_text, category_slug, spending_type, hit_count.
3. Nêu ưu tiên: preference của user thắng default category nếu câu mới tương tự.
4. Vẫn phải tuân thủ income `spending_type=null`; category slug thuộc danh sách.

Guardrails:
- Exact-match preference chỉ áp dụng khi pattern dài ≥2 ký tự và trùng token sau normalize, tránh pattern quá rộng như `mua`.
- Nếu exact match dùng preference, set `confidence >= 0.95`, `reason="matched user preference: ..."` và tăng `hit_count`.
- Khi preference bị xoá ở `/settings`, không dùng lại trong prompt.
- Explicit preference parser chỉ tạo draft; user phải xác nhận ở UI.

### 4.4 Frontend

- `/settings`: thêm tab "Sở thích phân loại" cạnh quản lý category.
- `PreferenceTable`: pattern, ví dụ, category, spending type, số lần dùng, lần dùng gần nhất, nút xoá.
- `PreferenceStatementBox`: nhập "Tao coi giày là thiết yếu" → gọi parse → hiển thị draft pattern/category/type → xác nhận lưu.
- Trong `TransactionDraftReview`, nếu draft đến từ preference thì hiện badge "Theo sở thích đã học" và reason.
- Khi user sửa category/type trước khi lưu transaction, toast nhẹ "Đã học cách phân loại này" sau khi API trả success.

## 5. Task breakdown

- [ ] T1 Migration + ORM cho `classification_preferences`, `classification_feedback`
- [ ] T2 Pydantic schemas `PreferenceRead/Create`, `ClassificationFeedbackRead`, `PreferenceDraft`
- [ ] T3 Implement normalize: lowercase, strip diacritics, strip amount/slang, tokenize, unit tests tiếng Việt
- [ ] T4 `classification_preference_service`: exact match, top-5 retrieval, upsert, delete, hit_count
- [ ] T5 Gắn preference lookup vào `transactions/parse`: exact shortcut trước, few-shot sau
- [ ] T6 Mở rộng `transaction_service.create()` để record feedback/upsert preference khi final khác AI suggestion
- [ ] T7 Endpoint CRUD preferences + endpoint parse explicit preference
- [ ] T8 API tests cho correction → feedback + preference, delete preference, exact shortcut không gọi OpenAI
- [ ] T9 Golden tests before/after preference, mark `@pytest.mark.ai`
- [ ] T10 UI `/settings` tab preferences + explicit statement flow
- [ ] T11 UI badge/reason trong draft review khi dùng preference
- [ ] T12 Cập nhật OpenAPI types, docs/PROGRESS/handoff + commit `phase-03: classification learning`

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

cd ..\frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest)**
| # | Input / dữ liệu | Kỳ vọng |
|---|---|---|
| 1 | normalize `"Mua giày MLB 1.8 triệu"` | `mua giay mlb`, không còn `1.8 trieu` |
| 2 | normalize `"Grab về nhà 45 nghìn"` | `grab ve nha`, không còn amount |
| 3 | preference pattern `giay`, input `"Mua giày Nike 2tr"` | exact match preference, không gọi OpenAI, category/type theo preference |
| 4 | correction AI `shopping/non_essential` → final `shopping/essential` | tạo `classification_feedback`, upsert preference `giay`, hit_count ≥1 |
| 5 | correction income `salary/null` giữ nguyên | không tạo feedback |
| 6 | DELETE preference rồi parse lại `"Mua giày Nike 2tr"` | không dùng preference đã xoá |
| 7 | explicit `"Tao coi giày là thiết yếu"` | parse draft pattern `giay`, spending_type `essential` |
| 8 | exact pattern quá rộng `mua` | không shortcut nếu service đánh dấu pattern không đủ cụ thể |

**Golden set (`pytest -m ai`)**
| # | Bước | Input | Kỳ vọng |
|---|---|---|---|
| 1 | Before preference | Mua giày MLB 1.8 triệu | amount `1800000`, expense, category `shopping`, spending_type có thể `non_essential` |
| 2 | Correction | User sửa draft #1 thành `shopping` + `essential` | preference pattern chứa `giay`, final type `essential` |
| 3 | After preference | Mua giày Nike 2tr | predicted `shopping` + `essential`, `matched_preference_id` khác null |
| 4 | Explicit preference | Tao coi giày là thiết yếu | draft pattern `giay`, type `essential` |
| 5 | Similar brand | Đặt giày Adidas 1tr2 | predicted `shopping` + `essential` |
| 6 | Không liên quan | Mua áo 450k | không bị preference `giay` ảnh hưởng |
| 7 | Food correction | Cafe với khách 200k sửa thành `food/non_essential` | lần sau "cafe 2 lít" dự đoán `non_essential` |
| 8 | Income unaffected | Nhận lương 25 triệu | `salary`, `spending_type=null` |
| 9 | Irregular preference | Sửa laptop là bất thường | lần sau "sửa màn hình laptop 900k" dự đoán `irregular` |
| 10 | Delete preference | Xoá preference `giay`, nhập "Mua giày Nike 2tr" | không có `matched_preference_id` |

Pass threshold: exact shortcut deterministic 100%; after-preference category/type đúng 100% cho cases có exact pattern; cases few-shot không exact category/type đúng ≥85%; không case nào dùng preference đã xoá.

**Kịch bản thao tác UI**
1. Quick add "Mua giày MLB 1.8 triệu" → sửa spending type thành Thiết yếu → Lưu → toast "Đã học cách phân loại này".
2. Quick add "Mua giày Nike 2tr" → draft tự là Thiết yếu và có badge "Theo sở thích đã học".
3. Mở `/settings` → tab Sở thích phân loại thấy pattern `giay`; xoá pattern.
4. Nhập "Tao coi giày là thiết yếu" ở `/settings` → xem draft → xác nhận → preference xuất hiện lại.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` không cần API key xanh; `pytest -m ai` có threshold ghi ở Handoff
- [ ] Exact preference path được test không gọi OpenAI
- [ ] `/settings` xem/xoá/tạo explicit preference hoạt động
- [ ] [data-model.md](../architecture/data-model.md) cập nhật nếu schema thực tế lệch
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật đánh dấu **M2 — Tracking loop hoàn chỉnh**
- [ ] Mục 9 Handoff notes đã điền
- [ ] Commit với message `phase-03: classification learning`

## 8. Rủi ro / câu hỏi mở

- Preference pattern quá rộng có thể gây phân loại sai hàng loạt; cần heuristic độ cụ thể và UI xoá dễ thấy.
- `classification_feedback.transaction_id` yêu cầu transaction đã lưu; nếu user bỏ draft thì không học.
- Explicit preference tiếng lóng ("Tao coi sneaker là thiết yếu") có thể cần synonym; Phase 3 chỉ dùng LLM parse + pattern raw, chưa có dictionary synonym.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
