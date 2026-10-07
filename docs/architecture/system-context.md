# System Context (C4 Level 1)

```mermaid
flowchart TB
    user(["Người dùng<br/>(single-user, cá nhân)"])
    app["AI Personal Finance Assistant<br/>Ghi chép, phân loại, lập ngân sách,<br/>review định kỳ, tư vấn"]
    openai["OpenAI API<br/>Chat Completions / Structured Outputs<br/>Vision, Embeddings"]
    bank["File sao kê ngân hàng<br/>(CSV / Excel, user tự tải về)"]
    receipt["Ảnh hoá đơn<br/>(user chụp / upload)"]
    kb["Tài liệu kiến thức tài chính<br/>(markdown / pdf do dev tuyển chọn)"]

    user -->|"Nhập giao dịch bằng câu tự nhiên,<br/>xem review, chat với Coach"| app
    bank -->|"Upload (Phase 14)"| app
    receipt -->|"Upload (Phase 13)"| app
    kb -->|"Ingest offline (Phase 16)"| app
    app -->|"Prompt + dữ liệu đã tổng hợp<br/>(không gửi dữ liệu thừa)"| openai
    openai -->|"JSON có cấu trúc / văn bản / vector"| app
```

## Ranh giới & dữ liệu gửi ra ngoài

| Dữ liệu | Gửi tới OpenAI? | Ghi chú |
|---|---|---|
| Câu nhập giao dịch | Có | Để parse thành structured transaction |
| Danh sách category + preference liên quan | Có | Làm context cho classifier |
| Số liệu tổng hợp tuần/tháng | Có | Review chỉ gửi metrics đã tính, không gửi toàn bộ lịch sử |
| Danh sách giao dịch chi tiết | Hạn chế | Chỉ top-N giao dịch liên quan khi cần giải thích |
| Ảnh hoá đơn | Có | Vision API (Phase 13) |
| Ghi chú giao dịch | Có | Để tạo embedding (Phase 15) |
| `OPENAI_API_KEY` | — | Chỉ nằm trong `.env` backend, không bao giờ xuống frontend |
