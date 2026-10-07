# Feature Map — Feature → Công nghệ / Course → Phase

| Feature | Công nghệ / chủ đề course | Phase | Ghi chú triển khai |
|---|---|---|---|
| Transaction CRUD | Python, FastAPI, SQLAlchemy | 1 | Nền móng deterministic |
| Natural language input | OpenAI API | 2 | Chat Completions |
| Categorization | LLM + Structured Outputs | 2 | Pydantic → JSON schema |
| Học preference phân loại | LLM + memory (few-shot động) | 3 | Bảng `classification_preference` |
| Budget engine | Python | 4 | 3 strategies |
| Budget vs Actual | Python, SQL aggregate | 5 | |
| Weekly Review | Agent workflow (LangGraph) | 6 | collect → highlight → write → validate |
| Monthly Review | Agent workflow (LangGraph) | 7 | Tái dùng graph |
| Anomaly / budget advisor | Python / thống kê (ML nhẹ) | 8 | median, CV, tỉ trọng giao dịch đơn lẻ |
| Flexible zones | Python / thống kê | 9 | mean ± std |
| Chatbot | LangChain | 10 | Tools bọc services |
| Budget tools | Function Calling | 10 | Read-only tools |
| Financial agent | LangGraph | 10 | ReAct + guard |
| Multiple tools | Agent | 10, 15, 16, 17 | Tool registry tăng dần |
| Goals + PYF | Python | 11 | |
| Cashflow forecast / recurring detection | Python | 12 | Phát hiện chu kỳ từ lịch sử |
| Receipt parsing | Vision (GPT-4o) | 13 | |
| CSV / Excel import | Python (pandas, openpyxl) | 14 | Batch classify |
| Spending search | Embeddings | 15 | `text-embedding-3-small` |
| Vector DB | pgvector (thay Pinecone trong course — xem ADR-002) | 15, 16 | Khái niệm tương đương: index, upsert, query top-k, metadata filter |
| Financial knowledge | RAG | 16 | Trích nguồn |
| What-if simulator | Python tools | 17 | |
| Retry / validation | OpenAI API best practices | 2 → 18 | `ai/openai_client` |
| Local / private AI (Llama 3), OCR/TTS (Hugging Face) | Ollama, HF | Ngoài phạm vi chính | Hướng mở rộng sau Phase 18: provider thay thế qua `openai_client` |
