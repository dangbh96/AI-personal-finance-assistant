# Phase 07 — Monthly Review Engine

| | |
|---|---|
| **ID** | `phase-07-monthly-review` |
| **Trạng thái** | Not started |
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

- [ ] T1 Migration + ORM/Pydantic schemas cho `monthly_reviews`
- [ ] T2 `analytics_service.get_review_metrics(period="month")`: income/expense/saved/savings rate/breakdown %
- [ ] T3 Tích hợp budget vs actual summary và weekly reflection answers vào metrics tháng
- [ ] T4 Mở rộng `detect_highlights` cho monthly: irregular items, vs previous month, budget variance lớn
- [ ] T5 Reuse `review_graph(period="month")` + prompt monthly + fallback template
- [ ] T6 Router `/api/v1/reviews/monthly*` + metrics preview + reflection endpoint
- [ ] T7 Unit/API tests deterministic + golden AI tests laptop irregular
- [ ] T8 Frontend `/reviews/monthly/[month]` với Recharts + summary cards + reflection
- [ ] T9 CTA sang Phase 8 `/budget/advice`
- [ ] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-07: monthly review engine`

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

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` thường xanh không cần API key; `pytest -m ai` xanh khi có key
- [ ] Monthly review reuse được `review_graph`; không copy workflow riêng
- [ ] M4 được đánh dấu trong [PROGRESS.md](../PROGRESS.md)
- [ ] Frontend chart không tự tính lại số tiền
- [ ] Handoff notes điền
- [ ] Commit `phase-07: ...`

## 8. Rủi ro / câu hỏi mở

- Savings rate khi income = 0: thống nhất trả `null` hoặc `0`; nên chọn `null` trong metrics để tránh hiểu sai, UI hiển thị "—".
- Nếu monthly review lấy weekly reflection chưa completed, chỉ đưa answer đã có; không ép user hoàn tất mọi weekly review.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
