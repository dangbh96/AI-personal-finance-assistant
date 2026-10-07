# ADR-004: Single-user trước, chừa user_id

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Mục tiêu là tập trung vào business logic và AI; auth tốn công mà không tăng giá trị demo ở giai đoạn đầu.

## Quyết định

Không có đăng nhập. App chạy local cho 1 người. Các bảng nghiệp vụ chính có cột `user_id UUID NULL` (chưa dùng) để thêm auth ở Phase 18 hoặc sau mà không cần migrate lớn. Unique constraint theo kỳ (`budget.period_month`, `weekly_review.week_start`) sẽ đổi thành `(user_id, ...)` khi bật multi-user.

## Phương án đã cân nhắc

Auth JWT ngay từ đầu.

## Hệ quả

Không được deploy public khi chưa có auth. Ghi rõ trong README.
