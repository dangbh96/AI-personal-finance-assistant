# ADR-004: Single-user trước, chừa user_id

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Mục tiêu là tập trung vào business logic và AI; auth tốn công mà không tăng giá trị demo ở giai đoạn đầu.

## Quyết định

Không có đăng nhập. App chạy local cho 1 người. Các bảng nghiệp vụ chính có cột `user_id UUID NULL` (chưa dùng) để thêm auth ở Phase 18 hoặc sau mà không cần migrate lớn. Unique constraint theo kỳ (`budget.period_month`, `weekly_review.week_start`) sẽ đổi thành `(user_id, ...)` khi bật multi-user.

## Follow-up Phase 18 (2026-10-22)

**Giữ nguyên single-user local, không bật auth.** Lý do: bật auth "nửa vời" nguy hiểm hơn không bật (mọi
query phải lọc `user_id`, unique theo kỳ phải đổi, backfill user mặc định, quản lý session/token) mà không
tăng giá trị demo. Biện pháp bù trong Phase 18:

- CORS chỉ cho origin cấu hình (`CORS_ORIGINS`, mặc định `http://localhost:3000`) và các method thực dùng.
- Endpoint `/admin/*` (báo cáo chi phí AI, smoke-data) chỉ đọc, không chứa nội dung prompt/câu trả lời.
- Docker compose chỉ map port ra `localhost` của máy dev; tài liệu ghi rõ **không deploy public**.

Khi cần multi-user: thêm bảng `users` (hoặc provider auth), backfill một user mặc định, chuyển các `user_id`
sang `NOT NULL`, đổi unique theo kỳ sang `(user_id, ...)` (`budgets.period_month`, `weekly_reviews.week_start`,
`monthly_reviews.month`, `import_batches.file_hash`…) và thêm dependency lấy user hiện tại cho mọi router.

## Phương án đã cân nhắc

Auth JWT ngay từ đầu.

## Hệ quả

Không được deploy public khi chưa có auth. Ghi rõ trong README.
