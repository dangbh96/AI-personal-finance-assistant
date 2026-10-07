# Phase 13 — Receipt OCR

| | |
|---|---|
| **ID** | `phase-13-receipt-ocr` |
| **Trạng thái** | Not started |
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
- Golden AI set 5 ảnh mẫu trong `backend\tests\ai_golden\receipts\` (to be collected): supermarket, restaurant, coffee shop, blurry photo, handwritten.
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
2. Tạo uuid filename, lưu vào `UPLOAD_DIR\receipts\YYYY\MM\`.
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
- 5 ảnh trong `backend\tests\ai_golden\receipts\`: `supermarket.jpg`, `restaurant.jpg`, `coffee_shop.jpg`, `blurry_photo.jpg`, `handwritten.jpg`.
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

- [ ] T1 Migration `receipts` + `transactions.receipt_id`, settings `UPLOAD_DIR` nếu chưa có
- [ ] T2 File storage service: validate mime/size, uuid filename, sha256, safe relative path
- [ ] T3 Pydantic schemas `ReceiptExtraction`, receipt read, manual prefill/draft response
- [ ] T4 `ai/receipt_vision.py` + prompt `receipt_vision_v1.md` + OpenAI structured output
- [ ] T5 Map extraction → `TransactionDraft`, tái dùng classifier/category validation
- [ ] T6 Router `/api/v1/receipts/*` upload/list/detail/retry/confirm/file preview
- [ ] T7 Unit/API tests upload validation, failed status, confirm creates transaction `source='receipt'`
- [ ] T8 Golden AI tests `@pytest.mark.ai` với 5 ảnh mẫu + expected YAML placeholders
- [ ] T9 UI `/import` tab Hoá đơn: dropzone, preview, extraction panel
- [ ] T10 UI confirm/edit flow + failed/manual entry state + privacy note
- [ ] T11 Cập nhật docs/PROGRESS, Handoff notes, commit `phase-13: receipt ocr`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
cd backend; alembic upgrade head; ruff check .; pytest
$env:OPENAI_API_KEY="sk-..."; pytest -m ai
uvicorn app.main:app --reload --port 8000
cd ..\frontend; npm run gen:api; npm run lint; npm run dev
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | Upload `receipt.jpg` 1MB `image/jpeg` | 201, file lưu dưới `UPLOAD_DIR\receipts\YYYY\MM\{uuid}.jpg`, receipt `uploaded` rồi `extracted` nếu AI mock pass |
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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` mặc định xanh không cần API key; AI golden chỉ chạy bằng `pytest -m ai`
- [ ] Không log image bytes/base64 hoặc API key
- [ ] Upload path an toàn, filename uuid, max size/mime enforced cả client và server
- [ ] Receipt extraction chỉ tạo draft; transaction chỉ được tạo khi user confirm
- [ ] Golden set có 5 mẫu/expected hoặc Handoff ghi rõ mẫu nào chưa thu thập được
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done, Handoff notes điền
- [ ] Commit `phase-13: receipt ocr`

## 8. Rủi ro / câu hỏi mở

- HEIC/HEIF support phụ thuộc trình duyệt và OpenAI/client; nếu preview lỗi vẫn có thể upload, nhưng cần test thực tế.
- Hoá đơn Việt Nam có nhiều format, VAT/service charge làm model chọn nhầm subtotal; prompt và golden set phải ưu tiên "tổng thanh toán".
- File ảnh chứa dữ liệu cá nhân; Phase 18 nên thêm retention/xoá file và cảnh báo rõ hơn nếu deploy ngoài local.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
