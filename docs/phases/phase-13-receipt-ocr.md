# Phase 13 — Receipt OCR

| | |
|---|---|
| **ID** | `phase-13-receipt-ocr` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 2 |
| **Mở khoá** | Phase 18 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 2
2. [glossary.md](../product/glossary.md) — `Receipt`, `source = "receipt"`, money as VND integer
3. [vision.md](../product/vision.md) — Receipt OCR giảm công nhập liệu, AI trả draft user xác nhận
4. [system-context.md](../architecture/system-context.md) — ảnh hoá đơn gửi OpenAI, không gửi dữ liệu thừa
5. [containers.md](../architecture/containers.md) — `UPLOAD_DIR`, `uploads/`
6. [data-model.md](../architecture/data-model.md) — `receipts`, `transactions.receipt_id`
7. [backend-components.md](../architecture/backend-components.md) — `ai/receipt_vision`
8. [ai-architecture.md](../architecture/ai-architecture.md) — Vision + Structured Outputs, model từ env
9. [sequences.md](../architecture/sequences.md#5-đọc-hoá-đơn-phase-13)
10. [frontend-structure.md](../architecture/frontend-structure.md) — route `/import`
11. ADR [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: Phase 2 đã Done; có `TransactionDraft`, category classifier, endpoint tạo transaction từ draft đã xác nhận, `OPENAI_MODEL_FAST/SMART` và `UPLOAD_DIR` trong settings.

## 2. Mục tiêu & giá trị cho user

User upload ảnh hoá đơn để app đọc merchant/ngày/tổng tiền/items và tạo draft giao dịch. User vẫn kiểm tra/sửa trước khi lưu, giúp giảm công nhập liệu mà giữ nguyên nguyên tắc human-in-the-loop cho mọi dữ liệu tài chính.

## 3. Scope

**In scope**
- Bảng `receipts` + cột `transactions.receipt_id`.
- Endpoint upload multipart `POST /api/v1/receipts`, validate mime/size, lưu file dưới `UPLOAD_DIR` với uuid filename.
- Chấp nhận `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`; max size 10MB.
- `ai/receipt_vision.py` gọi model vision (`OPENAI_MODEL_SMART`, mặc định gpt-4o) với Structured Output `ReceiptExtraction`.
- Map `ReceiptExtraction` sang `TransactionDraft`, tái dùng classifier Phase 2/3 để chọn category/spending_type.
- Confirm flow: user sửa draft rồi gọi confirm; receipt chuyển `confirmed`.
- Failure handling: ảnh unreadable/AI lỗi → receipt `failed`, trả manual entry prefilled từ thông tin đoán được nếu có.
- Golden AI set 5 ảnh mẫu trong `backend/tests/ai_golden/receipts/` (to be collected): supermarket, restaurant, coffee shop, blurry photo, handwritten.
- UI `/import` tab "Hoá đơn": upload, preview image, extraction result, confidence, confirm/edit.
- Privacy note trong UI: ảnh gửi tới OpenAI để trích xuất, lưu local trong `UPLOAD_DIR`.

**Out of scope**
- Batch import nhiều hoá đơn cùng lúc.
- Tách một hoá đơn thành nhiều transactions.
- OCR offline/local model.
- Tự xoá ảnh theo retention policy (Phase 18).
- Nhận diện VAT/thuế chi tiết ngoài tổng tiền/items cơ bản.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`receipts`: `id UUID PK`, `user_id UUID NULL`, `file_path TEXT`, `mime_type TEXT`, `original_filename TEXT`, `file_size_bytes INT`, `sha256 TEXT`, `extracted JSONB`, `status TEXT CHECK status IN ('uploaded','extracted','confirmed','failed')`, `error_code TEXT NULL`, `error_message TEXT NULL`, `transaction_id UUID NULL FK transactions(id)`, timestamps.
- Index `(status, created_at DESC)`, optional unique `(sha256)` để cảnh báo upload trùng.
- `file_path` là path tương đối trong `UPLOAD_DIR`, ví dụ `receipts/2026/10/{uuid}.jpg`; không lưu absolute path trong DB.

`transactions`: thêm `receipt_id UUID NULL FK receipts(id)` nếu chưa có; khi confirm, transaction `source='receipt'`, `raw_input` chứa merchant + original filename, `ai_suggestion` chứa extraction/classification ban đầu.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| POST | `/api/v1/receipts` | Upload + extract ngay | multipart `file` | `{receipt,extraction?,transaction_draft?,status}` |
| GET | `/api/v1/receipts` | List receipts | `?status=&limit=20` | `[{id,status,merchant,total,created_at,transaction_id}]` |
| GET | `/api/v1/receipts/{id}` | Chi tiết receipt | — | `{receipt,extraction,transaction}` |
| POST | `/api/v1/receipts/{id}/retry` | Retry extraction cho failed/uploaded | — | `{receipt,extraction?,transaction_draft?}` |
| POST | `/api/v1/receipts/{id}/confirm` | Tạo transaction từ draft đã sửa | `TransactionCreate` | `TransactionRead` + receipt `confirmed` |
| GET | `/api/v1/receipts/{id}/file` | Serve ảnh local để preview | — | image response |

Upload flow:
1. Validate content type + extension + size <= 10MB.
2. Tạo uuid filename, lưu vào `UPLOAD_DIR/receipts/YYYY/MM/`.
3. Insert receipt `uploaded`.
4. Gọi `receipt_vision.extract(path)`; nếu pass, update `extracted`, `status='extracted'`.
5. Map sang draft: `direction='expense'`, `amount=total`, `occurred_on=date or today`, `note=f"{merchant} - hoá đơn"`, category/spending_type từ classifier dựa trên merchant/items.
6. Nếu fail unreadable/timeout: update `status='failed'`, `error_code`, `error_message`; response vẫn có `manual_prefill` nếu đọc được một phần.

### 4.3 AI

Model/env:
- `OPENAI_MODEL_SMART` dùng cho vision structured output (mặc định `gpt-4o`).
- `OPENAI_MODEL_FAST` dùng classifier Phase 2/3 để map category nếu cần.
- Mọi call qua `ai/openai_client` để có retry/timeout/token logging.

Structured output:
```python
class ReceiptItem(BaseModel):
    name: str
    qty: float | None = None
    amount: int  # VND, line total if available

class ReceiptExtraction(BaseModel):
    merchant: str | None
    date: date | None
    total: int | None
    currency: Literal["VND"] | str = "VND"
    items: list[ReceiptItem] = []
    confidence: float = Field(ge=0, le=1)
    unreadable_reason: str | None = None
```

Prompt `backend/app/ai/prompts/receipt_vision_v1.md`:
1. Trích xuất đúng dữ liệu nhìn thấy trên ảnh, không đoán nếu không chắc.
2. Tiền VND trả về integer đồng; bỏ dấu phân cách nghìn.
3. `total` ưu tiên dòng tổng thanh toán cuối cùng; nếu có nhiều tổng, chọn số khách phải trả.
4. Items chỉ lấy dòng hàng rõ ràng; nếu item mờ thì bỏ qua, không bịa.
5. Nếu ảnh quá mờ/không phải hoá đơn: `total=null`, `confidence < 0.5`, điền `unreadable_reason`.

Guardrails/privacy:
- Chỉ gửi ảnh và prompt trích xuất; không gửi toàn bộ lịch sử giao dịch.
- Không log base64/image bytes; chỉ log receipt id, model, token/latency, status.
- Nếu `confidence < 0.6` hoặc `total is None`, không tạo draft hoàn chỉnh; UI mở manual entry prefilled.
- Validate `total > 0`; currency khác VND trả 422/manual vì app chưa đa tiền tệ.

Golden tests `@pytest.mark.ai`:
- 5 ảnh trong `backend/tests/ai_golden/receipts/`: `supermarket.jpg`, `restaurant.jpg`, `coffee_shop.jpg`, `blurry_photo.jpg`, `handwritten.jpg`.
- File expected YAML cạnh ảnh chứa merchant/date/total.
- Pass threshold: total correct ≥ 4/5; merchant normalized match ≥ 3/5; unreadable/blurry không hallucinate total nếu expected `unreadable=true`.

### 4.4 Frontend

- `/import` thêm tab `Hoá đơn`.
- Components: `ReceiptUploadDropzone`, `ReceiptPreview`, `ReceiptExtractionPanel`, `ReceiptDraftForm`, `ReceiptHistoryTable`.
- Upload progress, validate client size/type trước khi gửi.
- Sau extraction: hiển thị merchant, date, total, items, confidence badge; draft cho user sửa category/spending_type/note/ngày/số tiền.
- Nút "Lưu giao dịch" gọi confirm; sau thành công link sang `/transactions`.
- Failed state: hiển thị lý do, nút "Nhập thủ công từ ảnh này", nút retry.
- Privacy note dưới dropzone: "Ảnh được lưu local và gửi tới OpenAI để đọc nội dung hoá đơn; không dùng cho mục đích khác trong app."

## 5. Task breakdown

- [x] T1 Migration `receipts` + `transactions.receipt_id`, settings `UPLOAD_DIR` nếu chưa có
- [x] T2 File storage service: validate mime/size, uuid filename, sha256, safe relative path
- [x] T3 Pydantic schemas `ReceiptExtraction`, receipt read, manual prefill/draft response
- [x] T4 `ai/receipt_vision.py` + prompt `receipt_vision_v1.md` + OpenAI structured output
- [x] T5 Map extraction → `TransactionDraft`, tái dùng classifier/category validation
- [x] T6 Router `/api/v1/receipts/*` upload/list/detail/retry/confirm/file preview
- [x] T7 Unit/API tests upload validation, failed status, confirm creates transaction `source='receipt'`
- [x] T8 Golden AI tests `@pytest.mark.ai` với 5 ảnh mẫu + expected YAML placeholders
- [x] T9 UI `/import` tab Hoá đơn: dropzone, preview, extraction panel
- [x] T10 UI confirm/edit flow + failed/manual entry state + privacy note
- [x] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-13: receipt ocr`

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
| 1 | Upload `receipt.jpg` 1MB `image/jpeg` | 201, file lưu dưới `UPLOAD_DIR/receipts/YYYY/MM/{uuid}.jpg`, receipt `uploaded` rồi `extracted` nếu AI mock pass |
| 2 | Upload PDF hoặc `text/plain` | 415/422, không tạo receipt/file |
| 3 | Upload ảnh 10.500.000 bytes | 413, message max 10MB |
| 4 | Mock extraction merchant "Co.opmart", date 2026-10-05, total 352.000, items 3 dòng | Draft `amount=352000`, `occurred_on=2026-10-05`, `direction='expense'`, note chứa Co.opmart |
| 5 | Mock confidence 0.42, total null, unreadable_reason "blurry" | Receipt `failed`, response có `manual_prefill`, không tạo transaction |
| 6 | Confirm receipt với amount 352.000, category food | Tạo transaction `source='receipt'`, `receipt_id` set; receipt `confirmed`, `transaction_id` set |
| 7 | Retry receipt failed sau mock pass | Status chuyển `extracted`, giữ cùng receipt id, không tạo file mới |
| 8 | `@pytest.mark.ai` golden 5 ảnh mẫu | Total correct ≥ 4/5; blurry/handwritten xử lý theo expected; không hallucinate khi unreadable |

**Kịch bản thao tác UI**
1. Mở `/import`, tab `Hoá đơn`, kéo ảnh supermarket rõ nét vào dropzone.
2. Thấy preview ảnh, loading, sau đó merchant/date/total/items và confidence.
3. Sửa category nếu cần, bấm "Lưu giao dịch" → được chuyển/link sang transaction mới.
4. Upload ảnh mờ → thấy failed/manual entry, có nút retry và form nhập tay prefilled.
5. Upload file `.pdf` hoặc ảnh >10MB → UI/API báo lỗi thân thiện.
6. Mở receipt history → thấy receipt confirmed/failed và link giao dịch nếu có.

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` mặc định xanh không cần API key; AI golden chỉ chạy bằng `pytest -m ai`
- [x] Không log image bytes/base64 hoặc API key
- [x] Upload path an toàn, filename uuid, max size/mime enforced cả client và server
- [x] Receipt extraction chỉ tạo draft; transaction chỉ được tạo khi user confirm
- [x] Golden set có 5 mẫu/expected hoặc Handoff ghi rõ mẫu nào chưa thu thập được
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [x] Commit `phase-13: receipt ocr`

## 8. Rủi ro / câu hỏi mở

- HEIC/HEIF support phụ thuộc trình duyệt và OpenAI/client; nếu preview lỗi vẫn có thể upload, nhưng cần test thực tế.
- Hoá đơn Việt Nam có nhiều format, VAT/service charge làm model chọn nhầm subtotal; prompt và golden set phải ưu tiên "tổng thanh toán".
- File ảnh chứa dữ liệu cá nhân; Phase 18 nên thêm retention/xoá file và cảnh báo rõ hơn nếu deploy ngoài local.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22 (bắt đầu 2026-10-21)
- **Đã làm:**
  - **Migration** `20261022_f74480029b52_receipt_ocr`: bảng `receipts` (cột plan + `draft JSONB`, `model TEXT`; CHECK `status`, `file_size_bytes > 0`; index `(status, created_at)`, `sha256` không unique; FK `transaction_id` `SET NULL`) + `transactions.receipt_id` (FK `SET NULL` + index). ORM `models/receipt.py`, enum `ReceiptStatus`. Chi tiết: [data-model.md § Phase 13](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế). `UPLOAD_DIR` đã có trong settings (tương đối → tính từ `backend/`).
  - **Deterministic, không AI:** `services/receipt_storage` (content type + đuôi + ≤ 10MB + **magic bytes**; HEIC thường bị trình duyệt gửi type rỗng / octet-stream → dựa vào đuôi + magic; mime lưu theo nội dung thật; tên file = uuid receipt; `resolve_path` chặn `..` / đường dẫn tuyệt đối / ổ đĩa; `vision_payload` / `to_jpeg` đổi HEIC/HEIF → JPEG bằng Pillow + pillow-heif). `services/receipt_mapping` (hàm thuần: `assess_extraction` — `total` > 0, VND, `confidence ≥ 0.6`; `build_draft` / `build_manual_prefill` / `extraction_warnings` / `merchant_pattern`). `services/receipt_service` (upload → `uploaded` commit → `analyzer` → `extracted` / `failed`; retry; detail / list; `confirm_receipt` 1 commit). `classification_preference_service.record_feedback` thêm `keyword` / `guess_keyword` (mặc định giữ hành vi Phase 3).
  - **AI:** `ai/receipt_vision.py` + `prompts/receipt_vision_v1.md` — `OPENAI_MODEL_SMART` (gpt-4o), ảnh data URL `detail=high`, Structured Output `ReceiptVisionOutput` (extraction + `category_slug` / `spending_type` / `classification_reason` trong cùng lời gọi), validate slug chi / `total` > 0 (sai → model sửa 1 lần), rồi tên cửa hàng exact-match sở thích đã học → theo sở thích (`classifier.match_preference`). Lỗi AI không raise → `ReceiptAnalysis(error_code)`. `openai_client.Message` nhận `content` dạng danh sách (text + image_url). Log không có ảnh / base64 (có test).
  - **API** (`api/routers/receipts.py`): `POST /receipts` (multipart `file`, `?today=`; 201 `ReceiptDetail` = `{receipt, status, extraction, transaction_draft, manual_prefill, warnings, duplicate_of, transaction}`; 415 `unsupported_file_type`, 413 `file_too_large`, 422 `empty_file`), `GET /receipts?status=&limit=1–100` (`{items[{id, status, original_filename, merchant, total, receipt_date, error_code, transaction_id, transaction_occurred_on, created_at}]}`), `GET /receipts/{id}`, `POST /receipts/{id}/retry` (409 `receipt_not_retryable` nếu đã `extracted` / `confirmed`), `POST /receipts/{id}/confirm` (body `ReceiptConfirm` → 201 `{transaction, receipt, learned_preference, pyf_proposal}`; 409 `receipt_already_confirmed`; dùng lại `category_*` 422), `GET /receipts/{id}/file` (HEIC → JPEG; 404 `receipt_file_missing`). `TransactionRead.receipt_id`. Dependency mới: `python-multipart`, `pillow`, `pillow-heif` (+ dev `pyyaml`).
  - **Frontend:** route `/import` (`ImportPage`, `?tab=receipt`, tab CSV khoá tới P14) → `ReceiptImportPanel` + `ReceiptUploadDropzone` (validate client, tiến độ XHR, ghi chú quyền riêng tư), `ReceiptPreview`, `ReceiptExtractionPanel`, `ReceiptDraftForm` (dùng `TransactionFields`), `ReceiptHistoryTable`; `lib/receipts.ts`; nav "Nhập hoá đơn"; `/transactions?month=YYYY-MM` + nút "Nhập từ hoá đơn"; badge 🧾 "Hoá đơn" trong bảng giao dịch; `lib/api.ts` export `errorMessage`. `gen:api` chạy lại.
  - **Test:** **913 pass** (+96, không cần key): `tests/unit/test_receipt_storage.py` (magic bytes, 415 / 413 / rỗng, tên file, đường dẫn an toàn, HEIC → JPEG thật bằng pillow-heif), `tests/unit/test_receipt_mapping.py` (test case 4, 5, ngưỡng confidence, VND alias, cảnh báo, prefill), `tests/api/test_receipts.py` (test case 1–3, 5–7 + AI chưa cấu hình, output sai 2 lần → `AI_INVALID_OUTPUT`, sửa được ở lần 2, HEIC octet-stream → model nhận JPEG + preview JPEG, upload trùng, không log base64, học theo cửa hàng rồi hoá đơn sau dùng sở thích, xác nhận từ form nhập tay, sai loại danh mục, body sai, xoá giao dịch giữ receipt, retry khi mất file, list / filter / detail).
  - **Golden (`pytest -m ai`, gpt-4o, 2026-10-22):** 5 ảnh **tổng hợp** (Pillow, cửa hàng / số liệu giả) trong `tests/ai_golden/receipts/` + `*.yaml`: tổng đúng **5/5** (ngưỡng 4), tên cửa hàng **4/4** (ngưỡng 3), ảnh nhoè `total = null` → `failed unreadable`, danh mục + loại chi tiêu 4/4 (chỉ báo cáo). Chạy 3 lần: tổng / cửa hàng / ngày như nhau cả 3 lần; lần đầu (prompt nháp) quán cà phê ra `essential` → chỉnh prompt (ăn ngoài / cà phê → `non_essential`, siêu thị / tạp hoá giữ `essential`), 2 lần sau phân loại 4/4. ~2.900 prompt token / ảnh, 2–3 s. Toàn bộ `pytest -m ai`: **19/19**.
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev), `ruff check .`, `ruff format --check .`, `pytest` (913), `pytest -m ai` (19), `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. Smoke với **DB tạm `pfa_smoke13`** + `UPLOAD_DIR=uploads/_smoke` (đã xoá cả hai): curl upload `supermarket.jpg` → `extracted` 352.000 / 2026-10-05 / food essential + cảnh báo tổng dòng hàng 369.000 ≠ 352.000; ảnh nhoè → `failed unreadable`; PDF → 415; 10.500.000 byte → 413 "…10MB…"; confirm → giao dịch `source=receipt`, confirm lại 409; `/file` 200 image/jpeg. `npm run start` → `/`, `/import`, `/import?tab=receipt`, `/transactions?month=2026-10`, `/calendar`, `/goals` 200. Kịch bản UI 1–6 trên trình duyệt: upload nhà hàng → preview + 748.440 ₫ + 4 dòng + độ tin cậy → đổi danh mục sang Giải trí → "Lưu giao dịch" → "Đã học cách phân loại cửa hàng này" + link sang `/transactions?month=2026-10` (badge Hoá đơn); ảnh nhoè → lý do + "Đọc lại" (vẫn mờ) + "Nhập thủ công từ ảnh này" (340k) → lưu; PDF / ảnh > 10MB → lỗi thân thiện phía client; lịch sử hiện confirmed / failed + link giao dịch, "Xem" mở lại chi tiết. Upload lại ảnh nhà hàng → draft Giải trí theo sở thích + cảnh báo trùng.
- **Lệch so với plan (và lý do):**
  - Phân loại nằm **trong cùng lời gọi vision** (`ReceiptVisionOutput` = `ReceiptExtraction` + `category_slug` / `spending_type` / `classification_reason`) thay vì gọi thêm classifier `OPENAI_MODEL_FAST`: Phase 2/3 không có classifier LLM độc lập (phân loại nằm trong NL parse), 1 lời gọi rẻ / nhanh hơn; phần "tái dùng classifier" là exact-match sở thích đã học theo **tên cửa hàng** (không theo dòng hàng — tránh khớp nhầm khi siêu thị có hàng chục món).
  - `receipts` thêm `draft JSONB` (draft gốc → `ai_suggestion` khi xác nhận, dựng lại được khi mở từ lịch sử) và `model TEXT`; `extracted` chứa thêm khoá `suggestion` (phân loại sau khi áp sở thích) để form nhập tay điền danh mục. `sha256` index **không unique** — upload trùng chỉ cảnh báo (`duplicate_of` + warning), không chặn.
  - Confirm nhận `ReceiptConfirm` (direction / amount / occurred_on / category_id / spending_type / note, `extra=forbid`) thay vì `TransactionCreate` đầy đủ: `source`, `raw_input`, `ai_suggestion`, `receipt_id` do backend đặt (client không giả được). Response `{transaction, receipt, learned_preference, pyf_proposal}` thay vì chỉ `TransactionRead`. Sequence diagram cũ ghi `POST /transactions {receipt_id}` → đổi theo plan § 4.2 (`/receipts/{id}/confirm`).
  - Response upload / retry / detail dùng chung `ReceiptDetail` (thêm `warnings`, `duplicate_of`, `transaction`); list trả `{items}` (quy ước repo) + `receipt_date`, `transaction_occurred_on` (link đúng tháng). Mọi route nhận `?today=` (ngày mặc định khi hoá đơn không có ngày).
  - Lỗi AI → receipt `failed` + `manual_prefill`, HTTP **201** (không 503) — ảnh đã lưu, user nhập tay / đọc lại. Chưa đủ điều kiện draft có mã riêng: `unreadable`, `total_missing`, `invalid_total`, `unsupported_currency` (khác VND → nhập tay, plan cho phép 422/manual), `low_confidence`, `image_unreadable`, `file_missing`, `category_missing`. Confirm được cả từ `failed` (form nhập tay); chỉ học sở thích khi có draft AI.
  - Học sở thích từ hoá đơn dùng tên cửa hàng (≤ 5 từ) thay cho keyword đoán từ ghi chú (ghi chú "X - hoá đơn" cho ra từ khoá vô nghĩa như "hoa", "co", "ca").
  - `ReceiptItem.amount` cho phép `null` (dòng hàng không rõ thành tiền — "không bịa"). `GET /receipts/{id}/file` đổi HEIC sang JPEG để xem trước (rủi ro § 8). `/transactions` nhận `?month=` để link sang giao dịch mới; nav thêm "Nhập hoá đơn".
  - Golden set là ảnh **tổng hợp** do `generate_receipts.py` vẽ (không dùng ảnh thật có bản quyền / dữ liệu cá nhân); "viết tay" dùng font Ink Free, dòng hàng không dấu (font thiếu vài glyph tiếng Việt dựng sẵn).
- **Nợ kỹ thuật / TODO để lại:**
  - Chưa xoá ảnh theo retention, chưa có endpoint xoá receipt / ảnh (Phase 18); file mồ côi nếu commit receipt lỗi giữa chừng được xoá ngay, nhưng không có job dọn định kỳ.
  - Golden 5 ảnh tổng hợp rất "sạch" so với ảnh chụp thật (nhăn, nghiêng mạnh, thiếu sáng, hoá đơn dài nhiều trang); nên bổ sung ảnh thật đã ẩn thông tin cá nhân khi có.
  - Ảnh gửi nguyên kích thước (≤ 10MB, base64 ~13MB) — chưa thu nhỏ trước khi gửi; nếu tốn token / chậm có thể resize cạnh dài ~2048px trong `vision_payload`.
  - Hoá đơn định kỳ (điện, internet) sau khi xác nhận chưa tự gắn khoản định kỳ khớp (`recurring_detection.within_tolerance`, handoff Phase 12) — chưa làm (ngoài scope).
  - Upload trùng chỉ cảnh báo; không chặn tạo giao dịch trùng từ 2 receipt cùng ảnh.
  - Chưa có test tự động frontend (Vitest / Playwright — Phase 18); kịch bản UI chạy tay bằng trình duyệt.
  - Tiến độ upload dùng `XMLHttpRequest` riêng (`lib/receipts.uploadReceipt`), không qua `apiRequest`.
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_receipt_storage.py tests/unit/test_receipt_mapping.py tests/api/test_receipts.py -q)`
  - `(cd backend && PYTHONIOENCODING=utf-8 pytest -m ai tests/ai_golden/test_receipt_vision_golden.py -s)` — in bảng tổng / cửa hàng / ngày / danh mục từng ảnh
  - `(cd backend && python tests/ai_golden/receipts/generate_receipts.py)` — sinh lại 5 ảnh tổng hợp (cần font Windows hoặc `RECEIPT_FONT_DIR`)
  - `curl -s -X POST "localhost:8000/api/v1/receipts?today=2026-10-22" -F "file=@backend/tests/ai_golden/receipts/supermarket.jpg;type=image/jpeg"`
  - `curl -s -X POST localhost:8000/api/v1/receipts/<id>/confirm -H 'Content-Type: application/json' -d '{"amount":352000,"occurred_on":"2026-10-05","category_id":"<food>"}'`
  - UI: `/import`, `/transactions?month=2026-10`.
- **Gợi ý cho phase tiếp theo (Phase 14 — CSV / Excel import):**
  - `/import` đã có `ImportPage` với tab (`?tab=`) — thêm `TabsTrigger value="csv"` (đang `disabled`) + nội dung, thêm `"csv"` vào `TABS`.
  - Tái dùng mẫu upload: `receipt_storage` (validate đuôi / content type / dung lượng, `upload_root()`, `resolve_path` an toàn, đường dẫn tương đối) — có thể tách phần chung thành `services/upload_storage`; `lib/receipts.uploadReceipt` (XHR có tiến độ) cho file CSV lớn. `python-multipart` đã có.
  - Tạo giao dịch nội bộ theo mẫu `receipt_service.confirm_receipt` (resolve category / spending type, `transaction_repository.add`, 1 commit); `transactions` chưa có `import_batch_id` / `dedup_hash` — thêm qua migration như `receipt_id`, và `TransactionRead.import_batch_id`.
  - Phân loại hàng loạt: chưa có classifier LLM độc lập (receipt phân loại trong lời gọi vision) — Phase 14 cần `classify_batch` riêng; sở thích exact-match dùng `classifier.match_preference(text, prefs, direction=…)`.
  - DB dev đã `alembic upgrade head` (có `receipts`). Postgres vẫn ở **port 5433**.
