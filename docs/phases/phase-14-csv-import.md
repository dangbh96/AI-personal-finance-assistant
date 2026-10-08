# Phase 14 — CSV/Excel Bank Statement Import

| | |
|---|---|
| **ID** | `phase-14-csv-import` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 3 phải Done |
| **Mở khoá** | Phase 18 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 3
2. [glossary.md](../product/glossary.md) — `source = "import"`, `ImportBatch`, `direction`, `spending_type`
3. [data-model.md](../architecture/data-model.md) — cột `transactions.import_batch_id`, `transactions.dedup_hash`, entity `IMPORT_BATCH`
4. [backend-components.md](../architecture/backend-components.md) — `services/import_service`, AI không ghi DB trực tiếp
5. [frontend-structure.md](../architecture/frontend-structure.md) — route `/import`
6. [ai-architecture.md](../architecture/ai-architecture.md) — batch classify 20 dòng/request, preference exact-match bỏ qua LLM
7. [sequences.md](../architecture/sequences.md#import-sao-kê-csv-phase-14) — preview → sửa → commit
8. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định: Phase 3 đã có transaction CRUD, category seed, parser/classifier, `classification_preferences`, feedback khi user sửa phân loại.

## 2. Mục tiêu & giá trị cho user

User import được sao kê ngân hàng CSV/XLSX hàng loạt, xem preview, sửa mapping/categorization trước khi commit. Import lại cùng file hoặc dòng trùng không tạo giao dịch trùng.

## 3. Scope

**In scope**
- Đọc `.csv`, `.xlsx` bằng `pandas` + `openpyxl`.
- Hỗ trợ encoding CSV: `utf-8`, `utf-8-sig`, fallback `cp1258`/`windows-1258`; tự đoán separator `,`, `;`, tab.
- Chuẩn hoá format ngân hàng Việt Nam: ngày `dd/mm/yyyy`, số tiền `1.500.000`, cột debit/credit riêng, amount âm/dương.
- Auto-guess column mapping + user override, lưu mapping profile theo bank.
- `import_batches` với `file_hash`; trả 409 nếu file đã commit.
- `dedup_hash = hash(date, amount, direction, normalized_description)` cho từng dòng; dòng trùng được đánh dấu trong preview và bỏ qua khi commit.
- Batch classify 20 dòng/request, tái dùng Phase 3 preferences; exact-match preference dùng luôn, không gọi LLM.
- Bulk edit category/spending type trong preview, commit trong một DB transaction.
- Fixture `backend/tests/fixtures/imports/` gồm 25 dòng, 2 duplicate, 1 bad row.

**Out of scope**
- Kết nối API ngân hàng trực tiếp.
- Reconcile số dư tài khoản/ví.
- Tự động commit không qua preview.
- Import file > 10 MB hoặc streaming rất lớn.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

`import_batches`: `id`, `user_id NULL`, `filename`, `file_hash UNIQUE`, `bank_name NULL`, `column_mapping JSONB`, `row_count`, `valid_count`, `duplicate_count`, `bad_count`, `committed_count`, `status` (`previewed|committed|failed`), timestamps.

Thêm vào `transactions`:
- `import_batch_id UUID NULL FK import_batches(id)`
- `dedup_hash TEXT NULL`
- unique partial index `ux_transactions_dedup_hash` trên `dedup_hash WHERE dedup_hash IS NOT NULL`

Mapping profile quyết định lưu bằng bảng riêng `import_mapping_profiles`: `id`, `bank_name`, `headers_hash`, `column_mapping JSONB`, `date_format`, `decimal_style`, `last_used_at`, timestamps. Unique `(bank_name, headers_hash)`.

Chuẩn hoá row:
- `direction = "expense"` nếu debit > 0 hoặc amount < 0; `direction = "income"` nếu credit > 0 hoặc amount > 0.
- `amount` luôn `abs(value)` dạng số nguyên đồng.
- `normalized_description`: lowercase, trim, collapse whitespace, bỏ mã giao dịch quá nhiễu nếu nằm trong cột riêng; không bỏ nội dung merchant.

### 4.2 Backend (services, API)

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| POST | `/api/v1/imports/preview` | Upload file, parse, guess mapping, classify draft | `multipart/form-data file, bank_name?` | `ImportPreviewResponse` gồm `batch`, `mapping`, `rows`, `summary`; 409 nếu `file_hash` đã committed |
| PATCH | `/api/v1/imports/{id}/mapping` | User đổi mapping, parse lại preview | `{column_mapping, date_format?}` | Preview mới + suggestions |
| POST | `/api/v1/imports/{id}/commit` | Tạo transaction từ các dòng đã chọn | `{rows:[{row_index, category_id, spending_type, selected, note?}]}` | `{created_count, skipped_duplicate_count, bad_count}` |
| GET | `/api/v1/imports/{id}` | Lấy lại batch preview/summary | — | Batch + rows đã lưu tạm trong JSON |
| GET | `/api/v1/imports/mapping-profiles` | Danh sách profile theo bank | `?bank_name=` | `[{bank_name, headers_hash, column_mapping}]` |

Pydantic schemas:
```python
class ColumnMapping(BaseModel):
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None

class ImportPreviewRow(BaseModel):
    row_index: int
    occurred_on: date | None
    amount: int | None
    direction: Literal["income", "expense"] | None
    note: str
    dedup_hash: str | None
    status: Literal["valid", "duplicate", "bad"]
    error: str | None = None
    suggested_category_id: UUID | None = None
    suggested_spending_type: Literal["essential", "non_essential", "irregular"] | None = None
    confidence: float | None = None

class ImportCommitRequest(BaseModel):
    rows: list[ImportCommitRow]
```

`services/import_service.py` chịu trách nhiệm đọc file, guess mapping, normalize, dedup, commit transaction. `ai/classifier.classify_batch_import(rows, preferences)` chỉ trả suggestion, không ghi DB.

### 4.3 AI

- Model: `OPENAI_MODEL_FAST` cho batch classify; không dùng `OPENAI_MODEL_SMART`. Nếu thiếu key, preview vẫn chạy với category `other`/`other_income` và `confidence = 0`.
- Prompt outline: gửi tối đa 20 dòng `{note, amount, direction, occurred_on}`, danh sách category hợp lệ, top preference liên quan; yêu cầu trả list suggestion theo đúng `row_index`.
- Exact-match preference từ Phase 3 được áp dụng trước; các dòng đã match không đưa vào prompt.
- Guardrails: không tự đổi amount/date/direction; chỉ gợi ý category/spending_type; nếu không chắc thì `other` + confidence thấp; giọng văn lý do trung lập.

### 4.4 Frontend

- Route `/import`, tab "Sao kê CSV/Excel" dùng chung màn hình upload của Phase 13.
- Step 1 Upload: chọn bank name tuỳ chọn, hiển thị encoding/separator đoán được.
- Step 2 Mapping: bảng cột file → trường chuẩn; cảnh báo nếu thiếu date/description hoặc thiếu amount/debit-credit.
- Step 3 Preview: 25–100 dòng đầu, checkbox chọn dòng, badge duplicate/bad, inline edit category/spending type/note, bulk edit theo selection.
- Step 4 Commit summary: created/skipped/bad, link sang `/transactions?source=import&import_batch_id=...`.

## 5. Task breakdown

- [ ] T1 Thêm dependencies `pandas`, `openpyxl` và migration `import_batches`, `import_mapping_profiles`, cột/index trên `transactions`
- [ ] T2 Implement file reader CSV/XLSX: encoding fallback, separator sniff, giới hạn size/type an toàn
- [ ] T3 Implement auto column mapping + lưu/tải mapping profiles theo bank/header
- [ ] T4 Implement normalize amount/date/description + `file_hash` + `dedup_hash`
- [ ] T5 Implement preview API, 409 khi file_hash đã committed
- [ ] T6 Tích hợp Phase 3 preferences + batch classify 20 dòng/request
- [ ] T7 Implement commit API trong DB transaction, bỏ qua duplicate, rollback toàn bộ nếu lỗi không recover được
- [ ] T8 Tạo fixtures `backend/tests/fixtures/imports/` (VCB CSV utf-8-sig, Techcombank cp1258, XLSX) với 25 rows/2 duplicates/1 bad row
- [ ] T9 Pytest parser, dedup, API preview/commit, AI golden batch classify
- [ ] T10 UI `/import` upload → mapping → preview → bulk edit → commit
- [ ] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-14: csv import`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
(cd backend && alembic upgrade head && ruff check . && pytest tests/unit/test_import_service.py tests/api/test_imports.py)
(cd backend && pytest -m ai tests/ai_golden/test_import_classification.py)
(cd frontend && npm run gen:api && npm run lint && npm run dev)
```

**Test cases (pytest)**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|
| 1 | CSV utf-8-sig, separator `;`, 25 rows | Preview `row_count=25`, `valid_count=22`, `duplicate_count=2`, `bad_count=1` |
| 2 | CSV cp1258 có mô tả "Ăn trưa quán bún" | Decode đúng tiếng Việt, không lỗi ký tự |
| 3 | Amount `"1.500.000"` ở debit | `direction=expense`, `amount=1500000` |
| 4 | Cột credit `25.000.000` | `direction=income`, category gợi ý `salary` nếu note lương |
| 5 | 2 dòng cùng date/amount/direction/description | Cùng `dedup_hash`, dòng sau `status=duplicate` |
| 6 | Dòng ngày `32/13/2026` | `status=bad`, commit không tạo transaction |
| 7 | Import lại file đã committed | POST preview trả 409 `IMPORT_ALREADY_COMMITTED` |
| 8 | 20 dòng chưa có preference | Classifier được gọi đúng 1 request |
| 9 | 5 dòng exact-match preference | 5 dòng skip LLM, vẫn có suggestion đúng |
| 10 | Commit 22 dòng hợp lệ | Tạo 22 transactions `source=import`, `import_batch_id` đúng |

**Kịch bản thao tác UI**
1. Upload fixture VCB → thấy mapping tự đoán đúng date/description/debit/credit.
2. Đổi category 3 dòng "Grab" sang Đi lại bằng bulk edit.
3. Bỏ chọn 1 dòng duplicate, commit → summary tạo 22 dòng, bỏ qua 2 trùng, 1 lỗi.
4. Refresh `/transactions` lọc `source=import` → thấy các dòng vừa import.
5. Upload lại cùng file → thấy thông báo đã import, không có nút commit.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` không cần API key xanh; `pytest -m ai` pass khi có key
- [ ] Import commit là atomic và không tạo duplicate
- [ ] UI preview cho phép sửa/bulk edit trước khi ghi DB
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-14: csv import`

## 8. Rủi ro / câu hỏi mở

- Format sao kê ngân hàng rất đa dạng; nên bắt đầu với 2–3 fixture đại diện và cho user override mapping thay vì cố auto hoàn hảo.
- Một số mô tả chứa số dư/tài khoản; cần tránh gửi thông tin dư thừa vào prompt classify.
- Dedup theo description đã normalize có thể bỏ sót nếu bank thêm mã giao dịch khác nhau; chấp nhận vì user vẫn thấy preview.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
