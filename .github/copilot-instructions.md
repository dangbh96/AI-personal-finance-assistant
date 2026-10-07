# Copilot Instructions — AI Personal Finance Assistant

## Trước khi làm bất cứ việc gì

1. Đọc `docs/PROGRESS.md` để biết phase hiện tại và Handoff notes của phase trước.
2. Đọc file phase tương ứng trong `docs/phases/` và mọi tài liệu được liệt kê trong mục "1. Context cần đọc trước" của nó.
3. Chỉ làm việc thuộc scope của phase hiện tại. Việc ngoài scope → ghi vào mục "Rủi ro / câu hỏi mở" hoặc "Nợ kỹ thuật", không tự ý làm.

## Quy tắc bắt buộc

- **Tên gọi:** dùng đúng tên trong `docs/product/glossary.md` (ví dụ `spending_type` = `essential | non_essential | irregular`, `direction` = `income | expense`).
- **Tiền:** số nguyên đồng (`int` / `BIGINT`), luôn dương, chiều thể hiện qua `direction`. Không dùng float (ADR-007).
- **Lõi deterministic (ADR-005):** mọi phép tính tiền/tổng hợp/variance/forecast nằm trong `backend/app/services/`, có unit test, không gọi AI. AI chỉ tạo draft, diễn giải metrics đã tính, hoặc gọi tool read-only. AI không ghi DB khi chưa có user xác nhận.
- **Quy tắc phụ thuộc module:** theo `docs/architecture/backend-components.md` (`services` không import `ai`/`agents`).
- **Giọng văn AI:** 3 tầng Observation → Explanation → Action, tiếng Việt, xưng "bạn", không phán xét, không ra lệnh, không bịa số (`docs/architecture/ai-architecture.md`).
- **Model OpenAI** đọc từ env (`OPENAI_MODEL_FAST`, `OPENAI_MODEL_SMART`, `OPENAI_EMBEDDING_MODEL`), không hard-code. Mọi lời gọi qua `backend/app/ai/openai_client.py`.
- **Schema DB:** chỉ thay đổi qua Alembic migration. Bảng tên số nhiều snake_case. Cập nhật `docs/architecture/data-model.md` khi schema đổi.
- **Test:** `pytest` mặc định không cần OpenAI key; test gọi AI thật đánh dấu `@pytest.mark.ai` (chạy bằng `pytest -m ai`).
- **Bí mật:** không commit `.env`, không log API key, không gửi key xuống frontend.
- Môi trường dev là Windows + PowerShell: lệnh trong tài liệu dùng cú pháp PowerShell.

## Khi kết thúc (hoặc tạm dừng) một phase

1. Chạy hết mục "6. Verify" của phase.
2. Tick mục "7. Definition of Done".
3. Điền mục "9. Handoff notes" (đã làm gì, lệch plan ra sao, nợ kỹ thuật, gợi ý phase sau).
4. Cập nhật `docs/PROGRESS.md` (trạng thái, ngày, change log nếu lệch plan).
5. Cập nhật sơ đồ trong `docs/architecture/` nếu thiết kế thực tế khác.
6. Commit với message `phase-XX: <mô tả>`.
