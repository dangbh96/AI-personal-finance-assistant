# ADR-007: Tiền lưu dạng số nguyên đồng

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Float gây sai số; VND không có đơn vị lẻ phổ biến.

## Quyết định

Mọi số tiền là `BIGINT` (Python `int`) đơn vị **đồng**, luôn dương; chiều thu/chi thể hiện bằng `direction`. Phép chia (%, pro-rata, đề xuất budget) làm tròn bằng hàm chung `round_vnd(x, step)` trong `services/money.py`. API trả số nguyên, frontend format `vi-VN`. Cột `currency` không tạo cho tới khi cần đa tiền tệ.

## Phương án đã cân nhắc

`NUMERIC(14,2)` (thừa cho VND); float (sai số).

## Hệ quả

Nếu sau này hỗ trợ USD cần thêm currency + minor unit.
