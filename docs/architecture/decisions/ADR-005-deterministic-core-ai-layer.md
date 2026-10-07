# ADR-005: Lõi deterministic, AI là lớp diễn giải

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Dữ liệu tài chính cần chính xác tuyệt đối và có thể kiểm chứng; LLM có thể bịa số.

## Quyết định

Mọi phép tính tiền, tổng hợp, variance, trend, forecast, verdict advisor nằm trong `services/` (Python thuần + SQL, có unit test). AI chỉ (1) chuyển input tự nhiên thành draft có cấu trúc, (2) diễn giải metrics đã tính, (3) gọi tool read-only. AI không ghi DB trực tiếp; mọi ghi từ AI phải qua xác nhận của user. Narrative được validate: số xuất hiện phải có trong metrics.

## Phương án đã cân nhắc

Để LLM tự tính tổng từ danh sách giao dịch (nhanh làm nhưng sai số, không test được).

## Hệ quả

Phải viết nhiều logic thống kê thủ công, nhưng app vẫn dùng được khi AI lỗi/hết quota.
