# ADR-003: OpenAI là LLM chính

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

User có OpenAI API key. Cần structured outputs đáng tin cậy, vision, embeddings.

## Quyết định

Dùng **OpenAI** cho mọi tác vụ: `gpt-4o-mini` (tác vụ nhanh: parse, classify), `gpt-4o` (review, coach, vision), `text-embedding-3-small` (1536 dim). Model đọc từ env. Mọi lời gọi qua `ai/openai_client` để có thể thay provider sau (ví dụ Llama local qua Ollama với API tương thích OpenAI).

## Phương án đã cân nhắc

Llama local qua Ollama (miễn phí, riêng tư nhưng structured output / vision kém ổn định hơn) — giữ làm hướng mở rộng; Azure OpenAI.

## Hệ quả

Có chi phí API — dùng model nhỏ khi có thể, cache kết quả review. Dữ liệu tổng hợp gửi ra OpenAI (xem system-context.md).
