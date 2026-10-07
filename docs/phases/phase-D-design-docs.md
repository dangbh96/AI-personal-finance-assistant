# Phase D — System Design Diagrams & Plan Export

| | |
|---|---|
| **ID** | `phase-D-design-docs` |
| **Trạng thái** | Done |
| **Phụ thuộc** | — |
| **Mở khoá** | Phase 0 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [brainstorm-original.md](../product/brainstorm-original.md) — ý tưởng gốc

Trạng thái khi bắt đầu: thư mục rỗng, chưa phải git repo.

## 2. Mục tiêu & giá trị cho user

Có bộ tài liệu thiết kế + plan chi tiết từng phase nằm trong repo, để mỗi phase sau làm được ở một session riêng (nhiều ngày) mà không mất context.

## 3. Scope

**In scope**
- Khởi tạo git, `.gitignore`, `README.md`.
- Sơ đồ hệ thống bằng Mermaid trong `docs/architecture/`.
- ADR cho các quyết định chính.
- Tài liệu sản phẩm `docs/product/`.
- Plan từng phase `docs/phases/` theo template thống nhất.
- Cơ chế giữ context: `docs/README.md`, `docs/PROGRESS.md`, `.github/copilot-instructions.md`.

**Out of scope**
- Bất kỳ code ứng dụng nào.

## 4. Thiết kế chi tiết

### 4.1 Cấu trúc tài liệu

```
docs/
├── README.md                 # index + quy trình làm 1 phase
├── PROGRESS.md               # trạng thái mọi phase + change log
├── product/                  # vision, glossary, feature-map, brainstorm gốc
├── architecture/             # sơ đồ Mermaid + ADR
│   └── decisions/
└── phases/                   # _TEMPLATE + phase-D, phase-00 … phase-18
.github/copilot-instructions.md
```

### 4.2 Danh sách sơ đồ

| File | Loại |
|---|---|
| [system-context.md](../architecture/system-context.md) | C4 L1 |
| [containers.md](../architecture/containers.md) | C4 L2 |
| [backend-components.md](../architecture/backend-components.md) | Module + quy tắc phụ thuộc |
| [frontend-structure.md](../architecture/frontend-structure.md) | Bản đồ màn hình |
| [data-model.md](../architecture/data-model.md) | ERD |
| [core-loop.md](../architecture/core-loop.md) | Business loop |
| [ai-architecture.md](../architecture/ai-architecture.md) | AI tasks + LangGraph state graphs |
| [sequences.md](../architecture/sequences.md) | 7 sequence diagrams |
| [budget-adjustment.md](../architecture/budget-adjustment.md) | Decision tree + zones |
| [phase-roadmap.md](../architecture/phase-roadmap.md) | Dependency graph |

## 5. Task breakdown

- [x] T1 `git init`, `.gitignore`, `README.md`
- [x] T2 Glossary + data model (nền cho mọi tài liệu khác)
- [x] T3 Sơ đồ kiến trúc (system context, containers, components, frontend, core loop, AI, sequences, budget adjustment, roadmap)
- [x] T4 ADR-001 … ADR-007
- [x] T5 Product docs (vision, brainstorm gốc, feature map)
- [x] T6 `_TEMPLATE.md` + phase-D, phase-00 … phase-18
- [x] T7 `docs/README.md`, `docs/PROGRESS.md`, `.github/copilot-instructions.md`
- [x] T8 Verify render Mermaid + commit đầu tiên

## 6. Verify / Acceptance criteria

| # | Kiểm tra | Kỳ vọng |
|---|---|---|
| 1 | Parse toàn bộ khối Mermaid trong `docs/` | 0 lỗi |
| 2 | `docs/phases/` | 20 file phase + `_TEMPLATE.md`, mỗi file có đủ mục 1–9 |
| 3 | Link nội bộ giữa các file docs | Không có link chết |
| 4 | `phase-roadmap.md` | Khớp phụ thuộc trong header từng phase |
| 5 | `git log` | Có commit đầu tiên |

## 7. Definition of Done

- [x] Tất cả verify pass
- [x] PROGRESS.md: Phase D = Done

## 8. Rủi ro / câu hỏi mở

- Plan chi tiết của các phase xa (13–18) có thể lệch khi tới lúc làm — chấp nhận, cập nhật file phase ngay đầu phase đó.

## 9. Handoff notes

- **Ngày hoàn thành:** 2026-10-07
- **Đã làm:** Toàn bộ tài liệu thiết kế, ADR, plan 20 phase, cơ chế tracking.
- **Lệch so với plan:** Thêm `frontend-structure.md` và ADR-007 (tiền là số nguyên đồng) — không có trong plan ban đầu nhưng cần cho tính nhất quán.
- **Nợ kỹ thuật / TODO:** Không.
- **Lệnh hữu ích:** Xem Mermaid: VS Code Markdown Preview (cài extension "Markdown Preview Mermaid Support" nếu preview không render) hoặc push lên GitHub.
- **Gợi ý cho phase tiếp theo:** Bắt đầu [Phase 0](./phase-00-scaffolding.md). Kiểm tra Docker Desktop đã cài và chạy được.
