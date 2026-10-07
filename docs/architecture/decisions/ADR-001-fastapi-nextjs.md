# ADR-001: FastAPI (backend) + Next.js (frontend)

- **Trạng thái:** Accepted
- **Ngày:** 2026-10-07

## Bối cảnh

Cần web app full-stack, demo được nhiều kỹ thuật AI trong Python (OpenAI SDK, LangChain, LangGraph, pandas) và có UI hiện đại.

## Quyết định

Backend **FastAPI + Python 3.12+** (Pydantic v2 dùng chung cho API schema và AI structured output). Frontend **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui**. Giao tiếp REST JSON `/api/v1`.

## Phương án đã cân nhắc

Django (nặng, admin không cần thiết); Streamlit (nhanh nhưng UI hạn chế, khó làm luồng xác nhận draft phức tạp); full Next.js + TS AI SDK (lệch khỏi hệ sinh thái Python của curriculum).

## Hệ quả

2 ngôn ngữ, 2 dev server. Cần sinh TypeScript types từ OpenAPI để tránh lệch schema.
