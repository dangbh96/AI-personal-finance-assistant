# Phase 03 — Classification Learning

| | |
|---|---|
| **ID** | `phase-03-classification-learning` |
| **Trạng thái** | Done |
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

- [x] T1 Migration + ORM cho `classification_preferences`, `classification_feedback`
- [x] T2 Pydantic schemas `PreferenceRead/Create`, `ClassificationFeedbackRead`, `PreferenceDraft` (không tạo `ClassificationFeedbackRead` — chưa có endpoint đọc feedback)
- [x] T3 Implement normalize: lowercase, strip diacritics, strip amount/slang, tokenize, unit tests tiếng Việt
- [x] T4 `classification_preference_service`: exact match, top-5 retrieval, upsert, delete, hit_count
- [x] T5 Gắn preference lookup vào `transactions/parse`: exact shortcut trước, few-shot sau
- [x] T6 Mở rộng `transaction_service.create()` để record feedback/upsert preference khi final khác AI suggestion
- [x] T7 Endpoint CRUD preferences + endpoint parse explicit preference
- [x] T8 API tests cho correction → feedback + preference, delete preference, exact shortcut không gọi OpenAI
- [x] T9 Golden tests before/after preference, mark `@pytest.mark.ai`
- [x] T10 UI `/settings` tab preferences + explicit statement flow
- [x] T11 UI badge/reason trong draft review khi dùng preference
- [x] T12 Cập nhật OpenAPI types, docs/PROGRESS/handoff + commit `phase-03: classification learning`

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

cd ../frontend
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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` không cần API key xanh; `pytest -m ai` có threshold ghi ở Handoff
- [x] Exact preference path được test không gọi OpenAI
- [x] `/settings` xem/xoá/tạo explicit preference hoạt động
- [x] [data-model.md](../architecture/data-model.md) cập nhật nếu schema thực tế lệch
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật đánh dấu **M2 — Tracking loop hoàn chỉnh**
- [x] Mục 9 Handoff notes đã điền
- [x] Commit với message `phase-03: classification learning`

## 8. Rủi ro / câu hỏi mở

- Preference pattern quá rộng có thể gây phân loại sai hàng loạt; cần heuristic độ cụ thể và UI xoá dễ thấy.
- `classification_feedback.transaction_id` yêu cầu transaction đã lưu; nếu user bỏ draft thì không học.
- Explicit preference tiếng lóng ("Tao coi sneaker là thiết yếu") có thể cần synonym; Phase 3 chỉ dùng LLM parse + pattern raw, chưa có dictionary synonym.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-19
- **Đã làm:**
  - **DB** (migration `20261019_06a6605af7ab_classification_learning`): `classification_preferences` (unique `(user_id, pattern)` NULLS NOT DISTINCT, index `pattern`, `last_used_at DESC`) và `classification_feedback`. Chi tiết ở [data-model.md § Phase 3](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế). Đã thử `downgrade -1` / `upgrade head`.
  - **`services/classification_text.py`** (deterministic): `normalize_text` ("Mua giày MLB 1.8 triệu" → `mua giay mlb`, bỏ số tiền bằng `amount_text.amount_spans`), `normalize_pattern` (bỏ thêm `STOPWORDS`), `extract_keyword` (từ có nghĩa đầu tiên, + từ sau nếu là `HEAD_WORDS` như `tien`, `sua`, `phi`, `thue`, `sieu` → `giay`, `sua laptop`, `tien nha`), `is_specific`, `pattern_matches` (mọi token của pattern có trong câu, không cần liền nhau), `overlap`, `has_digits_besides_amounts`. `amount_text` thêm `amount_spans`, `remove_amounts`.
  - **`services/classification_preference_service.py`**: list/get/delete, `active_preferences` (bỏ danh mục đã ẩn), `find_exact` (pattern nhiều token nhất → `hit_count` → mới dùng), `related` (top-5 có token chung), `create_preference` (explicit, upsert theo pattern, 422 `preference_too_broad` / `category_not_found` / `category_archived` / `income_spending_type`), `record_feedback` (gọi trong `transaction_service.create_transaction_and_learn`, cùng commit).
  - **AI:** `ai/classifier.py` (suggestion từ preference, `apply_preferences` hậu kiểm từng draft của model, `format_few_shot`); `nl_transaction_parser` dùng prompt **v3** (thêm mục "Sở thích phân loại của người dùng" `{{preferences}}`) + `preference_shortcut`; `ai/preference_parser.py` + prompt `classification_preference_parse.v1.md`. Luồng chi tiết: [ai-architecture.md § 6](../architecture/ai-architecture.md#6-classification-memory-phase-3).
  - **API:** `GET/POST /classification-preferences`, `POST /classification-preferences/parse`, `DELETE /classification-preferences/{id}`; `POST /transactions/parse` trả thêm `drafts[].matched_preference_id` (+ `model="classification_preference"` khi không gọi AI); `POST /transactions` trả `TransactionCreateResult` = `TransactionRead` + `learned_preference`.
  - **Frontend:** `/settings` có tabs (shadcn `tabs`, `?tab=categories|preferences`): `PreferenceManager` = `PreferenceStatementBox` (câu → draft sửa được từ khoá/danh mục/loại → "Lưu sở thích") + bảng preference (từ khoá, ví dụ, danh mục, loại, số lần dùng, dùng gần nhất, xoá). Draft review: badge ✨ "Theo sở thích đã học" + reason; sau khi lưu, Quick add hiện "Đã học cách phân loại này: “giay” → Mua sắm · Thiết yếu. Xem / xoá". `gen:api` đã chạy lại.
  - **Test:** 259 pass (không cần key) — `tests/unit/test_classification_text.py` (45), `tests/api/test_classification_preferences.py` (43: đủ 8 test case mục 6 + shortcut bị chặn khi có ngày / nhiều khoản / chiều tiền ngược / `t7`, danh mục đã ẩn, few-shot chỉ preference liên quan, ghi đè theo từng draft, income correction, hit_count, sửa draft từ preference cập nhật chính preference đó, CRUD/validate, explicit parse + retry 502). Fixture `fake_ai` chuyển sang `tests/api/conftest.py`.
  - **Golden (`pytest -m ai -s`, `gpt-4o-mini`, 2026-10-19):** `test_classification_golden.py` 10 bước mục 6 — **exact 5/5 (100%)**, **model 6/6 (100%, ngưỡng 85%)**; bước 7: model tự đề xuất `food/non_essential` cho "Cafe với khách" nên không có correction, "cafe 2 lít" vẫn đúng qua model. Golden Phase 2 chạy lại với prompt v3: vẫn 100% mọi chỉ số (12/12 câu, 14/14 khoản). Prompt parse ~2.760 token/câu (v2 ~2.300) vì thêm mục sở thích.
  - **Verify:** `ruff check`, `ruff format --check`, `pytest`, `pytest -m ai`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 4 kịch bản UI mục 6 chạy trên trình duyệt với OpenAI thật: (1) "Mua giày MLB 1.8 triệu" → sửa Thiết yếu → "Đã học cách phân loại này"; (2) "Mua giày Nike 2tr" → badge "Theo sở thích đã học", backend không gọi OpenAI, lưu → `hit_count` = 2; (3) `/settings` tab Sở thích thấy `giay`, xoá được; (4) "Tao coi giày là thiết yếu" → draft `giay`/Mua sắm/Thiết yếu → lưu → xuất hiện lại. Dữ liệu thử đã xoá khỏi DB dev.
- **Lệch so với plan (và lý do):**
  - **Mỗi pattern 1 preference** (unique `(user_id, pattern)`) thay vì `(user_id, pattern, category_id, spending_type)`: tránh 2 cách phân loại mâu thuẫn; user đổi ý → cập nhật, `hit_count` đếm lại từ đầu.
  - **Shortcut không gọi OpenAI chỉ cho câu đơn giản** (1 khoản tiền, không nêu ngày, không có từ gợi ý chiều tiền ngược). Plan chỉ nói "không gọi LLM cho phần phân loại", nhưng ngày/số tiền/nhiều khoản vẫn cần model; câu phức tạp đi LLM rồi **hậu kiểm** từng draft exact-match theo preference (vẫn deterministic cho phần phân loại).
  - **`hit_count` tăng khi user lưu** draft dùng preference mà không sửa (không tăng lúc parse) — giữ nguyên tắc endpoint AI không ghi DB (ADR-005). Correction tạo/cập nhật preference tính 1 lần; explicit preference mới có `hit_count = 0`.
  - Correction trên draft **đã dùng preference** cập nhật chính preference đó (thay vì tạo keyword mới).
  - `reason` khi khớp preference viết tiếng Việt ("Theo sở thích phân loại đã học: …") thay vì "matched user preference: …" vì UI hiển thị reason. Confidence = 0.95.
  - `POST /transactions` trả `learned_preference` (schema `TransactionCreateResult`) để UI chỉ báo "Đã học" khi backend thực sự học (không phải cứ sửa là học — vd ghi chú không có từ khoá cụ thể). Thông báo là dòng trạng thái inline, không dùng toast (repo chưa có thư viện toast — như Phase 2).
  - `PreferenceCreate` nhận `category_slug` như plan; `example_text` tuỳ chọn; `spending_type` bỏ trống → default của danh mục. `POST /classification-preferences/parse` trả thêm `category_id`, `reason`, `example_text`, `model`, `warnings` (độ tin cậy thấp / sẽ thay sở thích cũ).
  - Không tạo `ClassificationFeedbackRead` (chưa có endpoint đọc feedback). Bảng tên `classification_feedback` (không thêm "s").
  - Ngoài plan: khi chưa cấu hình AI, câu khớp shortcut vẫn parse được (kiểm tra `ensure_configured` chuyển xuống ngay trước lời gọi OpenAI; câu không có số tiền giờ trả `422 amount_missing` trước cả `503 AI_NOT_CONFIGURED`). Ô Quick add vẫn bị khoá khi `/health` báo chưa cấu hình AI.
- **Nợ kỹ thuật / TODO để lại:**
  - Bỏ dấu làm trùng từ: "sữa" (milk) và "sửa" (repair) cùng thành `sua`; "quà" và "qua" (đã là stopword) — preference "sua laptop" có thể khớp "sữa … laptop" (hiếm). Phase 15 (embedding) có thể giải quyết.
  - Keyword từ correction là heuristic (từ có nghĩa đầu tiên): "MLB giày" → `mlb`; "Mua quà sinh nhật" → `sinh`. User xem/xoá ở `/settings` hoặc dạy lại bằng câu; chưa có sửa pattern tại chỗ (chỉ xoá + tạo lại).
  - Sửa phân loại sau khi lưu (PATCH ở `/transactions`) chưa ghi feedback / không học.
  - Few-shot chỉ lấy preference có token chung → không tổng quát hoá từ đồng nghĩa ("sneaker" vs `giay`) — đợi vector similarity (Phase 15).
  - Golden Phase 3 chỉ 1 kịch bản 10 bước; golden NL parse vẫn toàn câu "đẹp" (chưa thêm câu không dấu / sai chính tả như gợi ý Phase 2).
  - Xoá preference không hỏi xác nhận (dễ học lại).
  - Chưa có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/api/test_classification_preferences.py tests/unit/test_classification_text.py -q)`
  - `(cd backend && pytest -m ai -s -k classification)` — golden Phase 3 (in bảng ✓/✗ từng bước)
  - `curl -s localhost:8000/api/v1/classification-preferences`
  - `curl -s -X POST localhost:8000/api/v1/classification-preferences/parse -H 'Content-Type: application/json' -d '{"text":"Tao coi giày là thiết yếu"}'`
  - ⚠️ Sau `alembic revision --autogenerate` nhớ `alembic upgrade head` **trước** khi thử `alembic downgrade -1` — nếu DB chưa ở revision mới, `downgrade -1` sẽ hạ migration cũ hơn (xoá bảng `transactions`/`categories`).
- **Gợi ý cho phase tiếp theo (Phase 4 — Budget engine):**
  - Budget dùng `spending_type` của giao dịch; nhờ Phase 3 phân loại essential/non_essential ổn định hơn theo thói quen user.
  - Có thể tái dùng `services/classification_text.normalize_text` nếu cần map tên hũ/nhóm từ câu tự nhiên.
  - Mẫu "endpoint AI trả draft → user xác nhận → endpoint CRUD lưu" (parse explicit preference) dùng lại được cho wizard budget nếu có bước AI gợi ý.
