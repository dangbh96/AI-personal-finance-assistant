# Phase 07 — Monthly Review Engine

| | |
|---|---|
| **ID** | `phase-07-monthly-review` |
| **Trạng thái** | Done |
| **Phụ thuộc** | Phase 6 phải Done |
| **Mở khoá** | Phase 8 |
| **Milestone** | **M4 — Review loop (MVP sản phẩm)** |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của [Phase 6](./phase-06-weekly-review.md)
2. [glossary.md](../product/glossary.md) — `MonthlyReview`, `ReflectionAnswer`, `spending_type`
3. [vision.md](../product/vision.md) — Monthly Review và nguyên tắc không phán xét
4. [brainstorm-original.md](../product/brainstorm-original.md) — mục 6, 10, 15
5. [data-model.md](../architecture/data-model.md) — `monthly_reviews`, reuse `reflection_answers`
6. [ai-architecture.md](../architecture/ai-architecture.md) — reuse LangGraph `review_graph`
7. [budget-adjustment.md](../architecture/budget-adjustment.md) — monthly review mở khoá advisor ở Phase 8
8. [frontend-structure.md](../architecture/frontend-structure.md) — route `/reviews/monthly/[month]`, Recharts/Tremor
9. ADR [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [006](../architecture/decisions/ADR-006-langgraph-for-workflows.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu phase: Phase 6 đã có `review_graph(period="week")`, weekly metrics/highlights, validate/fallback, `reflection_answers`, UI review narrative; Phase 5 đã có budget vs actual summary cho tháng.

## 2. Mục tiêu & giá trị cho user

User xem được bức tranh tài chính tháng: thu, chi, tiết kiệm, savings rate, breakdown theo Thiết yếu/Không thiết yếu/Bất thường, so sánh tháng trước, budget vs actual, và insight rút ra từ các reflection tuần. Sau Phase 7, review loop tối thiểu hoàn chỉnh: theo dõi → review tuần → review tháng → chuẩn bị điều chỉnh tháng sau.

## 3. Scope

**In scope**
- Migration `monthly_reviews`.
- Mở rộng `review_graph(period="month")` reuse node Phase 6, thêm monthly metrics/highlights.
- Monthly metrics: income, expense, saved, savings rate, breakdown % theo spending type, vs previous month, irregular items highlighted, budget vs actual summary từ Phase 5, reflection answers của các weekly reviews trong tháng.
- UI `/reviews/monthly/[month]` với Recharts: spending type pie/bar, trend vs previous month, budget vs actual summary.
- Reflection question ở cấp tháng và lưu vào `reflection_answers`.
- CTA tạo Budget Advice ở cuối trang để Phase 8 nối vào.

**Out of scope**
- Tự động sửa budget hoặc tạo `budget_advice` (Phase 8).
- Flexible zone badge (Phase 9).
- Financial Coach chat (Phase 10).

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Tạo bảng `monthly_reviews`: `id UUID PK`, `user_id UUID NULL`, `month DATE UNIQUE NOT NULL`, `metrics JSONB NOT NULL`, `narrative JSONB NOT NULL`, `model TEXT`, `status TEXT DEFAULT 'generated' CHECK (status IN ('generated','completed'))`, timestamps.
- CHECK `extract(day from month) = 1`.
- `metrics.weekly_reflections` chứa summary/citations từ `reflection_answers` weekly trong tháng, không copy toàn bộ text dài nếu không cần.
- `narrative` cùng shape với Phase 6 để dùng chung component.

Reuse `reflection_answers`:
- `review_kind = 'monthly'`, `review_id = monthly_reviews.id`.
- `flagged_transaction_ids` cho phép chọn irregular/top transactions trong tháng.

### 4.2 Backend (services, API)

`analytics_service.get_review_metrics(period="month", month)` trả:
- `income_total`, `expense_total`, `saved = income_total - expense_total`, `savings_rate_pct` (làm tròn integer hoặc 1 chữ số theo helper chung).
- `by_spending_type`: amount + percent cho `essential`, `non_essential`, `irregular`.
- `vs_previous_month`: expense change %, income change %, saved change.
- `irregular_items`: transaction irregular lớn nhất; ví dụ laptop 15.000.000.
- `budget_actual_summary`: planned/actual/variance theo allocation/category từ Phase 5.
- `weekly_reflections`: câu trả lời reflection của các weekly review trong tháng, kèm flagged transactions.

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/reviews/monthly` | Danh sách monthly reviews | `?from=2026-09-01&to=2026-12-01` | `{items:[MonthlyReviewRead]}` |
| GET | `/api/v1/reviews/monthly/{month}` | Lấy review theo tháng | — | `MonthlyReviewRead` hoặc 404 |
| POST | `/api/v1/reviews/monthly` | Generate on-demand | `{month:"2026-10-01", regenerate:false}` | `MonthlyReviewRead` |
| POST | `/api/v1/reviews/monthly/{id}/reflections` | Lưu reflection tháng | `{answer, flagged_transaction_ids}` | `ReflectionAnswerRead` |
| GET | `/api/v1/reviews/monthly/{month}/metrics` | Debug/preview metrics deterministic | — | `MonthlyReviewMetrics` |

### 4.3 AI

`review_graph` gọi `OPENAI_MODEL_SMART`; fallback không gọi model. `OPENAI_MODEL_FAST` có thể dùng cho repair ngắn nếu Phase 6 đã hỗ trợ, nhưng không bắt buộc.

```python
from typing import Literal
from pydantic import BaseModel, Field

class ReviewNarrative(BaseModel):
    observation: str
    explanation: str
    notice: list[str] = Field(min_length=1, max_length=3)
    action: str | None
    reflection_question: str
    tone: Literal["neutral", "supportive"]

class MonthlyReviewMetrics(BaseModel):
    income_total: int
    expense_total: int
    saved: int
    savings_rate_pct: float
    by_spending_type: dict[str, dict[str, int | float]]
    vs_previous_month: dict[str, int | float]
    irregular_items: list[dict]
    budget_actual_summary: list[dict]
    weekly_reflections: list[dict]
```

Prompt outline:
- "Viết monthly financial review bằng tiếng Việt, giọng trung lập."
- Bắt buộc nêu nếu chi tăng do irregular item lớn; không quy kết thói quen khi evidence là one-off.
- Dùng câu kiểu "cao hơn tháng trước 12%" và "phần lớn mức tăng đến từ khoản mua laptop 15.000.000".
- Reflection hỏi user muốn giữ/điều chỉnh điểm nào trong tháng tới.

Guardrails:
- Cấm: "bạn tiêu quá nhiều", "lãng phí", "bạn phải", "bạn nên ngay lập tức", "kém kỷ luật".
- Mọi số (`12%`, `15.000.000`, `6.600.000`) phải xuất hiện trong `MonthlyReviewMetrics`.
- Không tự đưa verdict budget sai/hành vi sai; chỉ gợi ý "có thể xem tư vấn điều chỉnh ngân sách".

### 4.4 Frontend

- Route `/reviews/monthly/[month]`, ví dụ `/reviews/monthly/2026-10`.
- Components: `MonthlyReviewPage`, `MonthlySummaryCards`, `SpendingTypeChart` (Recharts), `BudgetActualMiniTable`, `IrregularItemsList`, `WeeklyReflectionDigest`, `ReviewNarrative`, `MonthlyReflectionForm`.
- CTA cuối trang: "Xem tư vấn điều chỉnh ngân sách" link `/budget/advice?month=2026-10-01`; nếu Phase 8 chưa có thì disable hoặc hiển thị "Mở ở Phase 8".
- Biểu đồ chỉ render dữ liệu API; không tính lại totals ở frontend.

## 5. Task breakdown

- [x] T1 Migration + ORM/Pydantic schemas cho `monthly_reviews`
- [x] T2 `analytics_service.get_review_metrics(period="month")`: income/expense/saved/savings rate/breakdown %
- [x] T3 Tích hợp budget vs actual summary và weekly reflection answers vào metrics tháng
- [x] T4 Mở rộng `detect_highlights` cho monthly: irregular items, vs previous month, budget variance lớn
- [x] T5 Reuse `review_graph(period="month")` + prompt monthly + fallback template
- [x] T6 Router `/api/v1/reviews/monthly*` + metrics preview + reflection endpoint
- [x] T7 Unit/API tests deterministic + golden AI tests laptop irregular
- [x] T8 Frontend `/reviews/monthly/[month]` với Recharts + summary cards + reflection
- [x] T9 CTA sang Phase 8 `/budget/advice`
- [x] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-07: monthly review engine`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_monthly_review_metrics.py tests/api/test_monthly_reviews.py
pytest -m ai tests/ai_golden/test_monthly_review.py

cd ../frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest deterministic)**
| # | Input / dữ liệu seed | Kỳ vọng |
|---|---|---|
| 1 | Tháng 2026-09: income 25.000.000, expense 18.400.000 | `saved = 6600000`, `savings_rate_pct = 26.4` |
| 2 | Breakdown: essential 9.200.000, non_essential 6.100.000, irregular 3.100.000, expense 18.400.000 | percent lần lượt 50, 33.2, 16.8 |
| 3 | Tháng 2026-10 expense 20.608.000, tháng 9 expense 18.400.000 | `expense_change_pct = 12` |
| 4 | Tháng 10 có transaction `electronics`, `irregular`, amount 15.000.000, note "Laptop" | `irregular_items[0].amount = 15000000`, category đúng |
| 5 | Budget food planned 4.000.000, actual 4.500.000 | budget summary variance 500.000 |
| 6 | 4 weekly reflection answers trong tháng, 3 flagged transaction ids | metrics có đủ digest + ids |
| 7 | POST reflection monthly với transaction ngoài tháng | 422 |

**Golden set AI (`@pytest.mark.ai`)**
| # | Metrics / highlights | Automatic checks |
|---|---|---|
| 1 | Month 2 có laptop irregular 15.000.000, expense cao hơn tháng trước 12% | Narrative nhắc `15.000.000`, `laptop`, `12%`, quy nguyên nhân tăng cho irregular item |
| 2 | Cùng metrics trên | Không chứa banned phrases; không dùng "bạn tiêu quá nhiều" |
| 3 | Metrics không có số 20.000.000 | Narrative không được sinh số 20.000.000 |
| 4 | Budget actual có food vượt 500.000 | Có thể nhắc food, nhưng không kết luận `adjust_budget` trước Phase 8 |

**Kịch bản thao tác UI**
1. Mở `/reviews/monthly/2026-10` → bấm "Tạo review tháng" → thấy cards Thu/Chi/Tiết kiệm/Savings rate.
2. Xem chart breakdown: Essential/Non-essential/Irregular đúng số API.
3. Narrative hiển thị câu trung lập kiểu "cao hơn tháng trước 12%; phần lớn mức tăng đến từ laptop 15.000.000".
4. Nhập reflection tháng, tick giao dịch laptop → lưu thành công.
5. Bấm CTA `/budget/advice?month=2026-10-01` → điều hướng đúng (Phase 8 sẽ implement nội dung).

## 7. Definition of Done

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` thường xanh không cần API key; `pytest -m ai` xanh khi có key
- [x] Monthly review reuse được `review_graph`; không copy workflow riêng
- [x] M4 được đánh dấu trong [PROGRESS.md](../PROGRESS.md)
- [x] Frontend chart không tự tính lại số tiền
- [x] Handoff notes điền
- [x] Commit `phase-07: ...`

## 8. Rủi ro / câu hỏi mở

- Savings rate khi income = 0: thống nhất trả `null` hoặc `0`; nên chọn `null` trong metrics để tránh hiểu sai, UI hiển thị "—".
- Nếu monthly review lấy weekly reflection chưa completed, chỉ đưa answer đã có; không ép user hoàn tất mọi weekly review.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:** 2026-10-21
- **Đã làm:**
  - **Migration** `20261021_79e40a3c073b_monthly_review`: `monthly_reviews` (UNIQUE `month`, CHECK ngày 1, `status generated|completed`). ORM `MonthlyReview` trong `models/review.py`.
  - **Deterministic (services):**
    - `review_metrics`: `share_pct` (% 1 chữ số, half-up, `None` khi mẫu ≤ 0), `increase_driver`, `irregular_items`, `compute_monthly_metrics`, `build_review_metrics` (highlights chung + phần riêng tháng — graph và endpoint preview dùng chung).
    - `analytics_service`: `ReviewData` thêm `budget` / `reflections` (chỉ kỳ tháng), `summarize_budget` (rút gọn `BudgetStatusRead`), `get_monthly_budget_summary` (budget active/closed; nháp → `None`), `preview_review_metrics`.
    - `review_service`: `save_monthly_review`, `get_monthly*`, `list_monthly`, `add_monthly_reflection` (khoản chi trong tháng), `weekly_reflections_in_month`, `to_monthly_read(s)`; `_validate_flagged` / `_add_reflection` dùng chung tuần–tháng. `budget_service.allocation_label` + `JAR_LABELS`.
    - `review_narrative`: `strip_ids` / `metrics_payload` (bỏ mọi khoá ID — thay danh sách loại trừ cứng của Phase 6), `_monthly_problems`, `format_pct`, fallback tháng (`MONTHLY_REFLECTION_QUESTION`), cụm cấm mới.
  - **AI:** prompt `review_narrative_month.v1.md`; `review_writer` chọn prompt theo `metrics.period`. **Graph** `review_graph`: state thêm `budget`, `reflections`; `PERSISTERS["month"]`; `get_or_generate_monthly_review`.
  - **API** `api/routers/monthly_reviews.py`: `GET /reviews/monthly?from&to`, `POST /reviews/monthly {month, regenerate, today}` (200; `month` phải ngày 1 → 422 `validation_error`; tháng tương lai → 422 `month_not_started`), `GET /reviews/monthly/{month}` (ngày bất kỳ trong tháng; 404 `monthly_review_not_found`), `GET /reviews/monthly/{month}/metrics?today` (preview, không AI, không lưu), `POST /reviews/monthly/{id}/reflections` (201).
  - **Frontend:** `recharts 3.10` (+ peer `react-is`). Route `/reviews/monthly` (`MonthlyReviewIndex`), `/reviews/monthly/[month]` (`MonthlyReviewPage` + `MonthlySummaryCards`, `SpendingTypeChart`, `IrregularItemsList`, `WeeklyReflectionDigest`, `BudgetActualMiniTable`, `HighlightList`, `ReviewNarrative title="Nhìn lại tháng"`, `ReflectionForm kind="monthly"`, CTA), `/budget/advice` (trang giữ chỗ Phase 8). `ReflectionForm` / `FlagTransactionPicker` tổng quát hoá theo `kind` (tuần giữ nguyên hành vi). Nav "Review" sáng cho mọi `/reviews/*`. `gen:api` đã chạy lại.
  - **Test:** 491 pass (+51): `tests/unit/test_monthly_review_metrics.py` (28 — test case 1–4, `share_pct`, `increase_driver`, digest/dedup, số được phép không chứa ID, validate khoản bất thường / cụm verdict / số bịa, fallback tháng luôn hợp lệ), `tests/api/test_monthly_reviews.py` (23 — generate + budget (test 5), fallback, retry khi thiếu khoản bất thường, fail 3 lần → fallback, regenerate giữ reflection, tháng trước trống, tháng đang chạy, budget nháp, digest phản tư tuần (test 6), get/list/preview, reflection tháng (test 7), id review tuần ≠ review tháng). Dữ liệu dùng chung `tests/monthly_dataset.py`.
  - **Golden AI** `tests/ai_golden/test_monthly_review.py`: **2/2 pass** với `gpt-4o` (lần gọi đầu qua validate; có `12%`, laptop, `15.000.000 ₫` trong phần Why; không có `20.000.000`, không verdict ngân sách; chịu được prompt phán xét). Golden tuần chạy lại vẫn 2/2.
  - **Verify:** `alembic upgrade head`, `ruff check`, `ruff format --check`, `pytest`, `pytest -m ai tests/ai_golden/test_monthly_review.py tests/ai_golden/test_weekly_review.py`, `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 5 bước UI mục 6 chạy trên trình duyệt (DB dev, `?today=2026-11-02`): tạo review 10/2026 (gpt-4o, ~48s) → cards Thu/Chi/Tiết kiệm/Tỉ lệ; chart khớp API (7.800.000 / 6.200.000 / 15.000.000 — 26,9% / 21,4% / 51,7%); narrative "tăng 87%… phần lớn mức tăng đến từ khoản mua laptop 15.000.000 ₫"; phản tư + tick Laptop → "Đã phản tư"; CTA → `/budget/advice?month=2026-10-01`.
- **Lệch so với plan (và lý do):**
  - Giữ tên trường chung `income` / `expense` / `net` của `PeriodMetrics` (thay cho `income_total` / `expense_total`), thêm `saved` (= net) cho rõ nghĩa; `vs_previous_month` trải phẳng thành `income_change(_pct)`, `expense_change(_pct)` (đã có), `previous_saved`, `saved_change`, `previous_savings_rate_pct`. `by_spending_type` giữ số tiền (như tuần), % nằm ở `spending_type_pct` — để narrative/fallback/UI dùng chung schema.
  - Thêm `regular_expense*`, `irregular_change`, `increase_driver` (deterministic) để AI và validate biết khi nào mức tăng do khoản một lần — validate bắt buộc nêu khoản bất thường lớn nhất trong trường hợp này. `increase_driver = null` khi tháng trước không có chi.
  - `savings_rate_pct` = `null` khi thu = 0 (theo mục 8). % thay đổi vẫn là số nguyên như Phase 6; tỉ trọng / tỉ lệ tiết kiệm 1 chữ số.
  - "Phản tư tuần trong tháng" = review tuần có **Thứ Hai** thuộc tháng (tuần 28/09–04/10 thuộc tháng 9). Digest cắt câu trả lời 300 ký tự, bỏ giao dịch đã xoá, tổng hợp `flagged_count/total` theo giao dịch khác nhau.
  - Cụm cấm thêm áp dụng cả review tuần (giọng văn nhất quán). Gom số được phép / dựng prompt bỏ ID tổng quát theo tên khoá.
  - Thêm `/reviews/monthly` (index) và trang giữ chỗ `/budget/advice` để CTA điều hướng được (plan cho phép disable — chọn trang giữ chỗ để kịch bản UI 5 chạy được).
  - Trang tháng cập nhật tại chỗ sau khi lưu phản tư (giữ thông báo "Đã ghi nhận"); trang tuần giữ hành vi cũ (tải lại).
  - DB dev: thêm giao dịch "Laptop" 15.000.000 (Điện tử, bất thường, 10/10/2026) qua API để chạy kịch bản; đã tạo review tháng 10/2026 (gpt-4o, 2 phản tư). Tháng 10 dev vì vậy +87% so với tháng 9 (không phải 12% như ví dụ plan — số 12% nằm ở dữ liệu test).
- **Nợ kỹ thuật / TODO để lại:**
  - gpt-4o lần gọi đầu vẫn ~48s (prompt tháng ~7.000 token vì metrics có `by_category`, budget lines, highlights). Có thể rút gọn metrics gửi model (bỏ `previous_*` chi tiết, `by_category` danh mục 0đ) nếu cần nhanh hơn; chưa có streaming.
  - Allowed numbers vẫn là tập giá trị (không theo ngữ cảnh) — model có thể gán số thật cho ý khác. Golden chưa kiểm tra quan hệ số ↔ ý.
  - Câu trả lời phản tư tuần của user đi vào prompt tháng (prompt injection rủi ro thấp vì app 1 người dùng và output đã được validate).
  - `monthly_reviews` UNIQUE `month` cần thêm `user_id` khi có auth. Chưa có banner nhắc review tháng (chỉ có banner tuần). Không có test tự động frontend (Phase 18).
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_monthly_review_metrics.py tests/api/test_monthly_reviews.py -q)`
  - `(cd backend && pytest -m ai tests/ai_golden/test_monthly_review.py -s)`
  - `curl -s "localhost:8000/api/v1/reviews/monthly/2026-10-01/metrics?today=2026-11-02"`
  - `curl -s -X POST localhost:8000/api/v1/reviews/monthly -H "Content-Type: application/json" -d '{"month":"2026-10-01","today":"2026-11-02"}'`
  - UI: `/reviews/monthly/2026-10?today=2026-11-02`, `/budget/advice?month=2026-10-01`.
- **Gợi ý cho phase tiếp theo (Phase 8 — Budget adjustment advisor):**
  - Evidence có sẵn trong `MonthlyReviewMetrics`: `budget.lines/over_lines` (planned/actual/variance/status), `irregular_items` + `increase_driver` (dấu hiệu `one_off`), `weekly_reflections` / `flagged_*` (dấu hiệu `adjust_behavior`), `highlights.repeated_clusters`. Phase 5 có `top_contributor` (≥ 60% phần vượt) cho từng dòng — dùng `analytics_service.get_budget_status` khi cần chi tiết hơn.
  - Thay trang giữ chỗ `frontend/src/app/budget/advice/page.tsx` bằng UI thật; CTA ở `MonthlyReviewPage` đã truyền `?month=YYYY-MM-01`.
  - `adjust_budget` / `adjust_behavior` hiện là **cụm cấm** trong narrative review (để review không tự kết luận) — Budget advisor dùng prompt/validate riêng, không dùng `BANNED_PHRASES` của review nguyên trạng.
