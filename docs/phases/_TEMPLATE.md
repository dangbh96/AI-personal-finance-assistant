# Phase XX — <Tên phase>

| | |
|---|---|
| **ID** | `phase-XX-<slug>` |
| **Trạng thái** | Not started / In progress / Done / Blocked (đồng bộ với [PROGRESS.md](../PROGRESS.md)) |
| **Phụ thuộc** | Phase … phải Done |
| **Mở khoá** | Phase … |
| **Milestone** | (nếu có) |

## 1. Context cần đọc trước

Đọc theo thứ tự trước khi code:
1. [PROGRESS.md](../PROGRESS.md) — trạng thái + handoff của phase trước
2. [glossary.md](../product/glossary.md) — tên dùng trong code
3. … (link các file architecture liên quan)

Trạng thái code giả định khi bắt đầu phase: …

## 2. Mục tiêu & giá trị cho user

…

## 3. Scope

**In scope**
- …

**Out of scope** (để phase khác / không làm)
- …

## 4. Thiết kế chi tiết

### 4.1 Data model / migration
…

### 4.2 Backend (services, API)
| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|

### 4.3 AI (nếu có)
Model, prompt outline, structured output schema, tools, guardrail.

### 4.4 Frontend
Route, component, hành vi.

## 5. Task breakdown

Mỗi task đủ nhỏ để làm và commit trong một lần ngồi.

- [ ] T1 …
- [ ] T2 …

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
# ví dụ
cd backend && pytest
```

**Test cases / golden set**
| # | Input / kịch bản | Kỳ vọng |
|---|---|---|

**Kịch bản thao tác UI**
1. …

## 7. Definition of Done

- [ ] Tất cả task ở mục 5 xong
- [ ] Tất cả verify ở mục 6 pass
- [ ] `pytest` (không cần API key) xanh
- [ ] Docs liên quan đã cập nhật (data-model, sequences… nếu lệch thiết kế)
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật trạng thái phase = Done
- [ ] Mục 9 Handoff notes đã điền
- [ ] Commit với message `phase-XX: …`

## 8. Rủi ro / câu hỏi mở

- …

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
