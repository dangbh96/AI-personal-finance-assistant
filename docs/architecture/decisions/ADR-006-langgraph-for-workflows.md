# ADR-006: LangGraph cho workflow AI nhiều bước

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Review cần nhiều bước có kiểm soát (collect → highlight → write → validate → retry/fallback). Coach cần vòng lặp tool-calling.

## Quyết định

Dùng **LangGraph** cho `review_graph` và `coach_graph`; tools định nghĩa bằng LangChain `@tool` bọc services. Tác vụ một bước (parse, classify, vision) gọi OpenAI SDK trực tiếp với Structured Outputs, không qua LangChain, cho đơn giản.

## Phương án đã cân nhắc

Tự viết vòng lặp tool-calling (ít phụ thuộc nhưng phải tự lo state/retry); dùng LangChain AgentExecutor (đã cũ).

## Hệ quả

Thêm dependency, phải pin version vì API LangGraph thay đổi nhanh.
