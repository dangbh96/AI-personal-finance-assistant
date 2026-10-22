# Phase 14 — CSV/Excel Bank Statement Import

| | |
|---|---|
| **ID** | `phase-14-csv-import` |
| **Trạng thái** | Done |
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

- [x] T1 Thêm dependencies `pandas`, `openpyxl` và migration `import_batches`, `import_mapping_profiles`, cột/index trên `transactions`
- [x] T2 Implement file reader CSV/XLSX: encoding fallback, separator sniff, giới hạn size/type an toàn
- [x] T3 Implement auto column mapping + lưu/tải mapping profiles theo bank/header
- [x] T4 Implement normalize amount/date/description + `file_hash` + `dedup_hash`
- [x] T5 Implement preview API, 409 khi file_hash đã committed
- [x] T6 Tích hợp Phase 3 preferences + batch classify 20 dòng/request
- [x] T7 Implement commit API trong DB transaction, bỏ qua duplicate, rollback toàn bộ nếu lỗi không recover được
- [x] T8 Tạo fixtures `backend/tests/fixtures/imports/` (VCB CSV utf-8-sig, Techcombank cp1258, XLSX) với 25 rows/2 duplicates/1 bad row
- [x] T9 Pytest parser, dedup, API preview/commit, AI golden batch classify
- [x] T10 UI `/import` upload → mapping → preview → bulk edit → commit
- [x] T11 Cập nhật docs/PROGRESS/handoff + commit `phase-14: csv import`

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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` không cần API key xanh; `pytest -m ai` pass khi có key
- [x] Import commit là atomic và không tạo duplicate
- [x] UI preview cho phép sửa/bulk edit trước khi ghi DB
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [x] Commit `phase-14: csv import`

## 8. Rủi ro / câu hỏi mở

- Format sao kê ngân hàng rất đa dạng; nên bắt đầu với 2–3 fixture đại diện và cho user override mapping thay vì cố auto hoàn hảo.
- Một số mô tả chứa số dư/tài khoản; cần tránh gửi thông tin dư thừa vào prompt classify.
- Dedup theo description đã normalize có thể bỏ sót nếu bank thêm mã giao dịch khác nhau; chấp nhận vì user vẫn thấy preview.

## 9. Handoff notes

> Điền khi kết thúc phase.

- **Ngày hoàn thành:** 2026-10-22 (bắt đầu 2026-10-21)
- **Đã làm:**
  - **Migration** `20261022_3c9e5d1a7b20_csv_import`: bảng `import_batches` (cột plan + `file_type`, `file_size_bytes`, `date_format`, `decimal_style`, `mapping_source`, `file_info JSONB`, `source_rows JSONB` (bảng thô để đổi mapping không cần upload lại), `rows JSONB` (dòng preview), `model`, `ai_error_code`, `committed_at`; `file_hash` UNIQUE; CHECK `status`, các count ≥ 0; index `created_at`), `import_mapping_profiles` (UNIQUE `(bank_name, headers_hash)`, `bank_name = ''` khi không nhập, + cột `headers`), `transactions.import_batch_id` (FK `SET NULL` + index) + `transactions.dedup_hash` + unique partial index `ux_transactions_dedup_hash … WHERE dedup_hash IS NOT NULL`. ORM `models/import_batch.py`. Chi tiết: [data-model.md § Phase 14](../architecture/data-model.md#ghi-chú-triển-khai-thực-tế). Dependency mới `pandas>=2.2`, `openpyxl>=3.1` (venv: pandas 3.0.6, openpyxl 3.1.5).
  - **Deterministic, không AI:** `services/import_reader` (đuôi `.csv` / `.xlsx` + content type cho phép + ≤ 10MB + ≤ 5.000 dòng; XLSX phải là zip, CSV không có byte NUL; `.xls` → 415 kèm hướng dẫn; CSV `utf-8-sig`/`utf-8` → `cp1258` + NFC; đoán dấu phân cách `,` `;` tab theo số cột ổn định nhất; đọc bằng `pandas` (CSV engine python, XLSX `openpyxl`, sheet đầu có dữ liệu, ô ngày → ISO, ô số → làm tròn 2 chữ số lẻ để bỏ sai số nhị phân như `165000.00000000003`)). `services/import_parsing` (hàm thuần: tìm dòng tiêu đề trong 30 dòng đầu (bỏ dòng mở đầu tên ngân hàng / số TK), tên cột duy nhất, `guess_mapping` theo alias tiếng Việt / Anh có thứ tự ưu tiên (cột số dư / mã tham chiếu bị chặn), `mapping_problems`, `guess_date_format` / `parse_date` (dd/mm, mm/dd, yyyy-mm-dd, năm 2 chữ số, kèm giờ, serial Excel), `guess_decimal_style` / `parse_amount` (`1.500.000`, `1,500,000.00`, `(x)`, `-x`, `x-`, `VND`/`đ`), chiều tiền theo ghi nợ / ghi có / dấu, `normalize_description`, `dedup_hash`, `file_hash`, `headers_hash`, `is_transfer_like`, `prompt_safe_description` (che token ≥ 5 chữ số), `parse_rows` + `mark_duplicates`). `services/import_service` (preview / đổi mapping / commit / profile; router truyền `classifier` như `analyzer` Phase 13).
  - **AI:** `ai/classifier.classify_batch_import` + prompt `import_classification.v1.md` — exact-match sở thích Phase 3 trước (không gửi model), còn lại gộp theo nội dung (cùng nội dung + chiều → gửi 1 lần), 20 dòng / request `OPENAI_MODEL_FAST`, song song ≤ 4, tối đa 300 nội dung / lần; validate đủ / đúng `row_index`, slug tồn tại + cùng loại với chiều, `spending_type` theo chiều → sai thì model sửa 1 lần. Lỗi AI không raise: dòng không có đề xuất → `other` / `other_income`, `confidence = 0`, `ai_error_code` + cảnh báo. Prompt chỉ có nội dung (đã che số dài), số tiền, chiều, ngày — không gửi cột số dư / tên file.
  - **API** (`api/routers/imports.py`): `POST /imports/preview` (multipart `file`, `bank_name?` → 201 `ImportPreviewResponse` = `{batch, file_info, mapping{column_mapping, date_format, decimal_style, source, profile_id, problems}, rows, summary, warnings}`; 409 `IMPORT_ALREADY_COMMITTED` + `import_batch_id`; 413 / 415 / 422 `empty_file` / `unreadable_file` / `unsupported_encoding` / `too_many_rows`), `PATCH /imports/{id}/mapping` (`{column_mapping, date_format?, decimal_style?}` → preview mới; 422 `invalid_mapping`; 409 nếu đã commit), `POST /imports/{id}/commit` (`{rows[{row_index, category_id, spending_type?, selected, note?}], save_mapping_profile}` → 201 `{created_count, skipped_duplicate_count, bad_count, not_selected_count, batch}`; 422 `import_row_not_found` / `no_rows_selected` / lỗi danh mục kèm "Dòng N: …"; 409 lần 2), `GET /imports/{id}`, `GET /imports/mapping-profiles?bank_name=`. `GET /transactions` (+ summary) nhận thêm `source`, `import_batch_id`; `TransactionRead.import_batch_id`. `DomainError.extra` → trường bổ sung trong body lỗi.
  - **Frontend:** tab "Sao kê CSV / Excel" ở `/import` (`?tab=csv`) → `CsvImportPanel`: `ImportUploadForm` (tên ngân hàng + gợi ý từ profile, kéo thả / chọn file, kiểm tra đuôi / 10MB, tiến độ XHR, ghi chú quyền riêng tư) → thẻ preview (tên file, bảng mã, dấu phân cách, sheet, dòng tiêu đề, badge đếm hợp lệ / trùng / lỗi / sở thích / AI / chưa phân loại, cảnh báo backend) → `ImportMappingEditor` (5 trường → cột, định dạng ngày, kiểu số, cảnh báo thiếu cột, "Áp dụng mapping") → `ImportPreviewTable` (lọc theo nội dung không dấu + trạng thái, checkbox chọn dòng (trùng / lỗi khoá; chuyển khoản nội bộ / có thể trùng nhập tay mặc định bỏ chọn), sửa ghi chú / danh mục / loại chi tiêu từng dòng, sửa hàng loạt cho dòng đang chọn trong danh sách lọc, 100 dòng / lần "Hiện thêm") → "Nhập N giao dịch" → tóm tắt + link `/transactions?source=import&import_batch_id=…`; 409 → thông báo + link, không có nút nhập. `lib/imports.ts`. `/transactions`: lọc "Nguồn", `?source=` / `?import_batch_id=` (bỏ lọc tháng, chip "Bỏ lọc"), nút "Nhập sao kê", badge Import. Nav "Nhập hoá đơn" → "Nhập dữ liệu". `gen:api` chạy lại.
  - **Test:** **1051 pass** (+138, không cần key): `tests/unit/test_import_service.py` (101: 3 fixture 25/22/2/1, cp1258, header có dòng mở đầu, mapping VCB / Techcombank / tiếng Anh / ưu tiên ngày, ngày / số tiền / kiểu số, chiều tiền, dòng lỗi, dedup trong file / đã có, chuyển khoản nội bộ, che số trong prompt, lỗi đọc file 413 / 415 / 422), `tests/api/test_imports.py` (37: test case 1–10 + AI chưa cấu hình / output sai → fallback, gộp 50 dòng → 3 request, prompt không chứa số TK, đổi mapping giữ đề xuất cũ, mapping thiếu / sai, profile lưu và dùng lại (có / không tên ngân hàng), cảnh báo chuyển khoản / trùng nhập tay, commit atomic, sửa hàng loạt → feedback nhưng không tạo sở thích, sở thích dùng → `hit_count` tăng, lỗi upload). Fixture giả `tests/fixtures/imports/` (`vcb_statement.csv` UTF-8 BOM `;`, `techcombank_statement.csv` cp1258 `,` số tiền có dấu, `statement.xlsx`) sinh bằng `generate_fixtures.py`.
  - **Golden (`pytest -m ai`, gpt-4o-mini, 2026-10-22):** `tests/ai_golden/test_import_classification.py` — VCB 22 dòng hợp lệ (21 nội dung → 2 request 20 + 1): lần đầu danh mục 21/22 (95%), loại chi tiêu 14/15 ("Sửa xe máy Honda" → `other`) → thêm gợi ý "sửa / bảo dưỡng xe → transport (irregular)" vào prompt → 2 lần chạy sau **22/22 (100%)** danh mục, **15/15** loại chi tiêu (ngưỡng 85% / 75%), lương → `salary`; sở thích "grab" → 3 dòng Grab không gửi model, đúng 1 request 18 dòng. Toàn bộ `pytest -m ai`: **21/21**.
  - **Verify:** `alembic upgrade head` + `downgrade -1` + `upgrade head` + `alembic check` (DB dev), `ruff check .`, `ruff format --check .`, `pytest` (1051), `pytest -m ai` (21), `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. Smoke với **DB tạm `pfa_smoke14`** (đã xoá): curl preview VCB / Techcombank (cp1258, "Ăn trưa quán bún bò") / XLSX → 25/22/2/1 với gpt-4o-mini thật, PATCH mapping (đổi cột nội dung → 24 hợp lệ, đổi lại → 22), PDF → 415, 10.485.761 byte → 413, id lạ → 404, commit → 22 / 2 / 1, upload lại → 409 + `import_batch_id`, mapping profile được lưu. `npm run start` → `/`, `/import`, `/import?tab=csv`, `/import?tab=receipt`, `/transactions`, `/transactions?source=import&import_batch_id=…`, `/settings` 200. Kịch bản UI 1–5 trên trình duyệt: upload VCB (ngân hàng "Vietcombank") → mapping tự đoán ngày / nội dung / ghi nợ / ghi có, UTF-8 BOM, `;`, dòng tiêu đề 4; lọc "grab" → sửa hàng loạt 3 dòng sang Đi lại; 2 dòng trùng bị khoá không chọn được → "Nhập 22 giao dịch" → "Đã nhập 22 · bỏ qua 2 trùng · 1 lỗi" → link sang `/transactions` lô import (22 giao dịch, badge Import, tổng thu 28.500.000 / chi 13.184.000); upload lại → "File này đã được import" + link, không có nút nhập; file mẫu có "THANH TOAN THE TIN DUNG" → cảnh báo + mặc định bỏ chọn.
- **Lệch so với plan (và lý do):**
  - `import_batches` lưu thêm `source_rows` (bảng thô), `rows` (preview), `file_info` (bảng mã / dấu phân cách / sheet / dòng tiêu đề / tên cột / `headers_hash` / `profile_id`), `file_type`, `file_size_bytes`, `date_format`, `decimal_style`, `mapping_source`, `model`, `ai_error_code`, `committed_at`: PATCH mapping / GET cần dựng lại preview mà không giữ file trên đĩa (không cần `UPLOAD_DIR`, không có file mồ côi). `import_mapping_profiles` thêm `headers`. Trạng thái `failed` giữ trong CHECK theo plan nhưng chưa có luồng nào đặt (lỗi đọc file → 4xx, không tạo batch; lỗi commit → rollback, batch vẫn `previewed`).
  - Đổi mapping: cột ngày / số tiền đổi mà định dạng gửi lên vẫn là định dạng đang lưu → backend đoán lại định dạng theo cột mới (UI luôn gửi giá trị đang hiển thị; tránh đọc `150,000` thành 150 khi upload chưa nhận ra cột số tiền); user chủ động chọn định dạng khác → dùng lựa chọn đó. `ColumnMapping` mọi trường đều optional (response cần trả mapping chưa đủ khi không đoán được cột); service kiểm tra đủ `date` + `description` + (`amount` **hoặc** `debit`/`credit`) → 422 `invalid_mapping`. `ImportPreviewRow` thêm `raw`, `duplicate_of_row`, `duplicate_existing`, `transfer_hint`, `possible_duplicate_transaction_id`, `warnings`, `reason`, `matched_preference_id`, `suggestion_source`. `row_index` = số dòng trong file / sheet (từ 1) để user đối chiếu.
  - POST preview trả **201** (tạo / làm mới batch). Upload lại file chưa commit → dùng lại batch cũ (cùng `file_hash`). 409 kèm `import_batch_id` (`DomainError.extra`) để UI mở danh sách giao dịch của lô; `ImportConflictResponse` trong OpenAPI. Commit nhận thêm `save_mapping_profile` (mặc định true), trả thêm `not_selected_count` + `batch`; dòng trùng / lỗi user chọn vẫn bị bỏ qua; dòng hợp lệ nhưng hash vừa xuất hiện trong DB (lô khác commit trước) → tính vào `skipped_duplicate_count`; không chọn dòng hợp lệ nào → 422 `no_rows_selected`.
  - Dedup kiểm tra cả hash đã có trong DB (giao dịch import trước đó, kể cả từ file / ngân hàng khác cùng nội dung) → `duplicate_existing`, không chỉ trùng trong file.
  - **Chuyển khoản nội bộ / trả nợ thẻ** (câu hỏi mở xuyên suốt): không có khái niệm tài khoản / ví nên không có danh mục "chuyển khoản"; nội dung khớp từ khoá (`tra no the`, `thanh toan the tin dung`, `chuyen khoan noi bo`, `gui tiet kiem`, `tat toan`, `nap vi`…) → `transfer_hint` + cảnh báo, UI **mặc định bỏ chọn**; user vẫn chọn nhập được. Thêm cảnh báo `possible_duplicate_transaction_id` khi có giao dịch nhập tay / nguồn khác cùng ngày + số tiền + chiều (cũng mặc định bỏ chọn).
  - Import **không tự học sở thích** từ chỉnh sửa (nội dung sao kê nhiễu, sửa hàng loạt dễ học sai từ khoá): sửa đề xuất → chỉ ghi `classification_feedback`; giữ đề xuất từ sở thích → `hit_count` + 1 (như Phase 3). `ai_suggestion` của giao dịch import chỉ lưu khi đề xuất đến từ sở thích / AI (không lưu fallback). Phân loại gom theo nội dung để tiết kiệm request (test case 8 vẫn đúng: 20 nội dung khác nhau → 1 request).
  - Commit kiểm tra toàn bộ dòng (danh mục / loại) trước khi ghi, mọi lỗi → rollback; `IntegrityError` (unique `dedup_hash` do lô khác commit song song) → 409 `import_conflict`.
  - UI: checkbox dùng chung cho "nhập dòng này" và phạm vi sửa hàng loạt (sửa hàng loạt áp dụng cho dòng đang chọn **trong danh sách đã lọc** — lọc "grab" rồi áp dụng); danh mục / loại chi tiêu trong bảng dùng `<select>` gốc (nhẹ hơn Base UI Select cho hàng trăm dòng). `/transactions` thêm bộ lọc "Nguồn"; `?import_batch_id=` bỏ lọc tháng. Nav đổi tên "Nhập dữ liệu".
- **Nợ kỹ thuật / TODO để lại:**
  - Chưa có "hoàn tác lô import" / xoá cả lô; xoá giao dịch import thì dòng đó import lại được từ file khác nhưng **file cũ vẫn bị chặn 409** (theo `file_hash`). Batch `previewed` không bao giờ bị dọn (bảng thô + preview nằm trong JSONB) — Phase 18 nên có job dọn / TTL.
  - Chỉ đọc sheet đầu có dữ liệu (cảnh báo nếu có nhiều sheet); chưa cho chọn dòng tiêu đề / sheet thủ công; chưa hỗ trợ `.xls`, PDF sao kê, file có mật khẩu; header `No.` (STT tiếng Anh) có thể bị nhận nhầm là cột ghi nợ (alias `no`).
  - Dedup theo nội dung đã chuẩn hoá: ngân hàng thêm mã giao dịch khác nhau vào nội dung → không nhận ra trùng (rủi ro § 8, user vẫn thấy preview); hai giao dịch thật giống hệt nhau trong cùng ngày (2 ly cà phê cùng giá) → dòng sau bị coi là trùng (do unique `dedup_hash`), user phải nhập tay.
  - Sửa ngày / số tiền của giao dịch đã import không cập nhật `dedup_hash` (cố ý: hash đại diện cho dòng sao kê gốc).
  - Không học sở thích từ import; nhận diện chuyển khoản nội bộ chỉ bằng từ khoá. Khi có khái niệm tài khoản / ví (câu hỏi mở) nên thay bằng ghép cặp tiền ra / tiền vào giữa các tài khoản.
  - Phân loại AI tối đa 300 nội dung khác nhau / lần (`AI_ROW_LIMIT`), phần còn lại để "Khác"; 5.000 dòng × JSONB vẫn ổn nhưng preview trả **toàn bộ** dòng một lần (chưa phân trang API).
  - openpyxl không chặn zip bomb chuyên biệt (chỉ giới hạn 10MB file nén); chưa cài `defusedxml`.
  - Chưa có test tự động frontend (Phase 18); kịch bản UI chạy tay bằng trình duyệt.
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_import_service.py tests/api/test_imports.py -q)`
  - `(cd backend && PYTHONIOENCODING=utf-8 pytest -m ai tests/ai_golden/test_import_classification.py -s)` — in bảng danh mục / loại chi tiêu / lý do từng dòng
  - `(cd backend && python tests/fixtures/imports/generate_fixtures.py)` — sinh lại 3 file sao kê giả
  - `curl -s -X POST localhost:8000/api/v1/imports/preview -F "file=@backend/tests/fixtures/imports/vcb_statement.csv;type=text/csv" -F "bank_name=Vietcombank"`
  - `curl -s -X POST localhost:8000/api/v1/imports/<id>/commit -H 'Content-Type: application/json' -d '{"rows":[{"row_index":5,"category_id":"<salary>"}]}'`
  - UI: `/import?tab=csv`, `/transactions?source=import&import_batch_id=<id>`.
- **Gợi ý cho phase tiếp theo (Phase 15 — Semantic search):**
  - Giao dịch import (`source='import'`) có ghi chú là nội dung sao kê (viết hoa, không dấu, có mã `#`) — khi tạo embedding nên dùng ghi chú + tên danh mục; có thể bỏ token chỉ gồm chữ số / mã giao dịch trước khi embed (tái dùng ý tưởng `import_parsing.prompt_safe_description`).
  - Backfill embedding cho cả giao dịch đã import (có thể vài trăm dòng một lần) → embed theo lô qua `openai_client`, tương tự gom 20 dòng / request của `classify_batch_import`.
  - Sở thích phân loại hiện chỉ exact-match theo token; Phase 15 có thể thêm vector similarity để phân loại dòng sao kê gần nghĩa ("GRAB*TRIP" ~ "grab bike") trước khi gọi LLM.
  - `GET /transactions` đã có `source` / `import_batch_id` — `/search` có thể dùng chung bộ lọc. Postgres vẫn ở **port 5433**.
