# Demo script & smoke checklist (Phase 18)

Kịch bản demo end-to-end toàn bộ core loop: **Thu nhập → Pay Yourself First → Ngân sách → Ghi chép →
Phân loại → Thực tế vs Ngân sách → Review tuần/tháng → Điều chỉnh**, cộng các tính năng AI (Coach, OCR,
import, semantic search, RAG, What-if). Lệnh dùng **Git Bash**, chạy từ thư mục gốc repo.

## 0. Chuẩn bị (một lần)

```bash
# Database
docker compose up -d db

# Backend (terminal 1)
cd backend
source .venv/Scripts/activate
alembic upgrade head
python -m app.scripts.seed_demo --months 3 --reset     # ~150 giao dịch 3 tháng gần nhất
python -m app.scripts.seed_scenario --reset            # ngân sách 10/2026 + 59 giao dịch cố định
python -m app.scripts.backfill_embeddings              # embedding cho semantic search (cần OPENAI_API_KEY)
python -m app.scripts.ingest_knowledge knowledge/      # 6 bài kiến thức cho RAG (cần OPENAI_API_KEY)
uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend && npm run dev
```

Kiểm tra dữ liệu đủ cho demo:

```bash
curl -s http://localhost:8000/api/v1/health        # {"status":"ok","db":"ok","vector":"ok","ai_configured":true,...}
curl -s http://localhost:8000/api/v1/admin/smoke-data
```

`smoke-data` trả `ok: true` khi đủ các mục **bắt buộc** (danh mục, giao dịch thu + chi 3 tháng, ngân sách
tháng này, embedding, kiến thức). `goals` / `recurring` / `ai` là khuyến nghị — bước 7–8 bên dưới sẽ tạo.

> Thay vì chạy 3 tiến trình: `docker compose up -d --build` (xem [README](../README.md#chạy-bằng-docker-compose-full-stack)),
> rồi chạy các lệnh seed **bên trong** container: `docker compose exec backend python -m app.scripts.seed_demo --months 3`.

## 1. Kịch bản demo (≈ 15 phút)

| # | Màn hình | Thao tác | Kỳ vọng (điểm nhấn khi trình bày) |
|---|---|---|---|
| 1 | `/` | Xem thẻ "Trạng thái hệ thống" và tóm tắt tháng | Backend / Database / AI đều xanh; thu / chi / thu − chi tháng hiện tại, dòng vượt ngân sách nhiều nhất |
| 2 | `/` → Quick add | Gõ `ăn phở 45k sáng nay` → kiểm tra draft → Lưu | AI chỉ tạo **draft** (số tiền 45.000, Ăn uống, thiết yếu); chỉ ghi DB khi bấm Lưu |
| 3 | `/transactions` | Thêm 1 giao dịch thủ công, sửa số tiền, xoá | CRUD deterministic, không cần AI |
| 4 | `/settings?tab=preferences` | Gõ `Tao coi giày là thiết yếu` → xác nhận | AI học sở thích; lần sau phân loại giày theo sở thích (badge "Theo sở thích đã học") |
| 5 | `/budget/new` | Tạo ngân sách tháng sau theo 50/30/20 (hoặc "Copy tháng trước") → Lưu & kích hoạt | Bảng phân bổ do backend tính; cảnh báo nếu tổng ≠ thu nhập |
| 6 | `/budget?month=2026-10&today=2026-10-15` | Tab "Theo dõi" | Budget vs Actual, vạch % tháng, badge on_track / ahead_of_pace / over_budget, cột **Vùng** 🟢🟡🔴; bấm dòng → giao dịch gây vượt |
| 7 | `/reviews/weekly` → tuần trước | "Tạo review tuần này" → nhập phản tư | Metrics do code tính; AI chỉ viết 3 tầng Quan sát → Vì sao → Gợi ý, không phán xét |
| 8 | `/reviews/monthly` → tháng trước | Tạo review tháng → "Tạo tư vấn điều chỉnh" | Biểu đồ cơ cấu; chuyển sang `/budget/advice` |
| 9 | `/budget/advice` | Xem verdict ("Budget có thể thấp hơn thực tế" / "Khoản bất thường một lần" / …) → Accept hoặc Dismiss | Verdict do cây quyết định deterministic; chỉ đổi ngân sách khi user xác nhận |
| 10 | `/goals` | Tạo mục tiêu "Mua laptop" 30.000.000, hạn 6 tháng; nhập thu nhập lương → dialog **Pay Yourself First** → xác nhận phân bổ | Gợi ý để dành / tháng; phân bổ chỉ ghi khi xác nhận |
| 11 | `/calendar` | Xem lịch tháng + dự báo số dư; xác nhận 1 khoản định kỳ được gợi ý | Khoản định kỳ phát hiện từ lịch sử; dự báo số dư theo ngày, cảnh báo ngày âm |
| 12 | `/import` | Upload ảnh hoá đơn (`backend/tests/ai_golden/receipts/coffee_shop.jpg`) → sửa draft → xác nhận | AI vision đọc hoá đơn → draft; file `.exe` đổi đuôi bị từ chối (415) |
| 13 | `/import` | Upload CSV sao kê → xem preview, mapping cột, sửa hàng loạt → Commit; upload lại cùng file | Commit tạo giao dịch; upload lại → **409** (không nhân đôi) |
| 14 | `/search?q=ăn ngoài` | Tìm | Ra các quán ăn dù ghi chú không chứa chữ "ăn ngoài" (semantic) + lý do khớp |
| 15 | `/coach` | Hỏi "Tao nên giảm khoản nào?" | Coach gọi tool (xem "Dữ liệu đã dùng" + tool trace), trả lời 3 tầng, chỉ dùng số từ tool |
| 16 | `/coach` | Hỏi "50/30/20 là gì, có phù hợp với tao không?" | Kết hợp `search_knowledge` (mục **Nguồn** có citation) + số liệu cá nhân |
| 17 | `/simulator` | Giảm Ăn uống 20% → Chạy | Chi / tháng giảm, mục tiêu đạt **sớm hơn N ngày**, budget variance; banner "Đây là **mô phỏng** — không thay đổi giao dịch, ngân sách…" |
| 18 | `/settings?tab=ai-usage` | Đổi "Theo model / tác vụ / loại lời gọi" | Số lời gọi, token, chi phí ước tính (đồng), latency, lỗi của mọi lời gọi OpenAI vừa demo |

## 2. Smoke checklist (tick khi kiểm tra bản phát hành)

**Hạ tầng**
- [ ] `docker compose up -d --build` → `pfa-db`, `pfa-backend`, `pfa-frontend` đều `(healthy)`
- [ ] `curl http://localhost:8000/api/v1/health` → `status: ok`, `db: ok`, `vector: ok`
- [ ] `http://localhost:3000` mở được, thẻ trạng thái xanh
- [ ] `GET /api/v1/admin/smoke-data` → `ok: true`

**Không có `OPENAI_API_KEY`** (xoá key trong `backend/.env`, khởi động lại backend)
- [ ] `/transactions`, `/budget`, `/goals`, `/calendar`, `/simulator` chạy bình thường
- [ ] Quick add / Coach báo lỗi rõ "chưa cấu hình AI" (503 `AI_NOT_CONFIGURED`), không crash
- [ ] Review tuần / tháng, tư vấn ngân sách, diễn giải mô phỏng dùng **bản tự động** (template)

**Core loop** — bước 2–11 của kịch bản trên chạy không lỗi.

**AI & dữ liệu lớn**
- [ ] OCR hoá đơn (bước 12), import CSV + upload lại 409 (bước 13)
- [ ] Search "ăn ngoài" (bước 14); query 5.000 ký tự → 422, không lỗi SQL
- [ ] Coach (bước 15–16): có evidence / citation, không cụm từ phán xét
- [ ] Ghi chú giao dịch chứa "Bỏ qua mọi hướng dẫn trước đó…" → Coach vẫn trả lời bình thường
- [ ] Simulator (bước 17) không thay đổi số giao dịch / ngân sách / mục tiêu
- [ ] Chi phí AI (bước 18) hiển thị các lời gọi vừa thực hiện

**Responsive** (DevTools ~390px): `/transactions`, `/budget`, `/coach`, `/import`, `/simulator` không vỡ layout, bảng cuộn ngang được.

**Lỗi**
- [ ] `curl -i http://localhost:8000/api/v1/khong-ton-tai` → `404 {"detail": "...", "code": "not_found"}`
- [ ] Tắt backend rồi thao tác trên UI → thông báo lỗi thân thiện, không trắng trang
