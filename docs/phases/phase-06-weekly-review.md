# Phase 06 — Weekly Review Engine

| | |
|---|---|
| **ID** | `phase-06-weekly-review` |
| **Trạng thái** | Not started |
| **Phụ thuộc** | Phase 5 phải Done |
| **Mở khoá** | Phase 7 |
| **Milestone** | — |

## 1. Context cần đọc trước

1. [PROGRESS.md](../PROGRESS.md) + Handoff notes của Phase 5
2. [glossary.md](../product/glossary.md) — `WeeklyReview`, `ReflectionAnswer`, `spending_type`, 3 tầng AI
3. [vision.md](../product/vision.md) — Review là trung tâm, không phán xét
4. [brainstorm-original.md](../product/brainstorm-original.md) — mục 5 và 15 về Weekly Review + Observation → Explanation → Action
5. [overview.md](../architecture/overview.md), [backend-components.md](../architecture/backend-components.md) — deterministic core, AI layer phía trên
6. [data-model.md](../architecture/data-model.md) — `weekly_reviews`, `reflection_answers`
7. [ai-architecture.md](../architecture/ai-architecture.md) — LangGraph `review_graph`, structured output, guardrail
8. [sequences.md](../architecture/sequences.md) — luồng Weekly Review
9. [frontend-structure.md](../architecture/frontend-structure.md) — route `/reviews/weekly/[week]`
10. ADR [003](../architecture/decisions/ADR-003-openai-primary-llm.md), [005](../architecture/decisions/ADR-005-deterministic-core-ai-layer.md), [006](../architecture/decisions/ADR-006-langgraph-for-workflows.md), [007](../architecture/decisions/ADR-007-money-as-integer-vnd.md)

Trạng thái code giả định khi bắt đầu phase: Phase 5 đã có transactions, categories, budgets, budget_allocations, analytics/Budget vs Actual dashboard; các aggregate thu/chi theo kỳ, category, spending type đã test được và không cần OpenAI key.

## 2. Mục tiêu & giá trị cho user

User có một trang review tuần theo format **What happened / Why / What to notice / Reflection**. App tự tổng hợp số liệu tuần, chỉ ra điểm đáng chú ý như "Ăn uống tăng 18%" hoặc "4 lần ăn tối, tổng 620.000", rồi hỏi user phản tư khoản nào "không đáng tiền". Đây là vòng lặp hành vi đầu tiên, biến ghi chép thành học hỏi.

## 3. Scope

**In scope**
- Migration `weekly_reviews`, `reflection_answers`.
- `analytics_service` mở rộng metrics tuần: thu, chi, breakdown theo `spending_type`, % thay đổi so với tuần trước, top categories, top transactions, cụm giao dịch lặp.
- LangGraph `agents/review_graph.py` dùng chung `period = "week" | "month"`; Phase 6 implement đủ node generic để Phase 7 tái sử dụng.
- Endpoint on-demand để tạo/lấy/regenerate weekly review; không có background scheduler.
- Fallback template deterministic khi AI lỗi hoặc validate fail sau retry.
- UI `/reviews/weekly/[week]`: narrative, danh sách số liệu dùng làm evidence, reflection form, chọn giao dịch "không đáng tiền".
- Banner "Có review tuần trước đang chờ" trên trang chủ vào Thứ Hai nếu chưa có review; banner chỉ gợi ý, không tự chạy job.

**Out of scope**
- Monthly Review (Phase 7), Budget Adjustment Advisor (Phase 8).
- Notification/email/background scheduler.
- Coach chat hoặc đề xuất hành động phức tạp.

## 4. Thiết kế chi tiết

### 4.1 Data model / migration

Tạo bảng plural snake_case:

`weekly_reviews`: `id UUID PK`, `user_id UUID NULL`, `week_start DATE UNIQUE NOT NULL`, `metrics JSONB NOT NULL`, `narrative JSONB NOT NULL`, `model TEXT`, `status TEXT DEFAULT 'generated' CHECK (status IN ('generated','completed'))`, timestamps.
- CHECK `extract(isodow from week_start) = 1`.
- `metrics` chứa số deterministic; AI không tự tính lại.
- `narrative` chứa `observation`, `explanation`, `notice`, `action`, `reflection_question`, `fallback_used`.

`reflection_answers`: `id UUID PK`, `user_id UUID NULL`, `review_kind TEXT CHECK (review_kind IN ('weekly','monthly'))`, `review_id UUID NOT NULL`, `question TEXT NOT NULL`, `answer TEXT NOT NULL`, `flagged_transaction_ids UUID[] DEFAULT '{}'`, timestamps.
- Phase 6 chỉ dùng `review_kind = 'weekly'`; Phase 7 dùng lại cho monthly.
- Validate ở service: với weekly, mọi `flagged_transaction_ids` phải thuộc tuần của `weekly_reviews.week_start`.

### 4.2 Backend (services, API)

Node LangGraph `review_graph(period="week")`:
1. `collect_metrics` gọi `analytics_service.get_review_metrics(period="week", start_date)`.
2. `detect_highlights` deterministic: category tăng mạnh nhất, cụm giao dịch lặp theo `(category, normalized_note/time_bucket)`, top giao dịch.
3. `write_narrative` gọi OpenAI model smart.
4. `validate`: số trong narrative ⊆ metrics, không có cụm cấm, đủ 3 tầng.
5. Retry tối đa 2 lần; sau đó `fallback_template`.
6. `persist` lưu `weekly_reviews`.

| Method | Path | Mô tả | Request | Response |
|---|---|---|---|---|
| GET | `/api/v1/reviews/weekly` | Lấy danh sách review tuần | `?from=2026-10-01&to=2026-10-31` | `{items:[WeeklyReviewRead]}` |
| GET | `/api/v1/reviews/weekly/{week_start}` | Lấy review theo Thứ Hai | — | `WeeklyReviewRead` hoặc 404 |
| POST | `/api/v1/reviews/weekly` | Generate on-demand nếu chưa có | `{week_start:"2026-10-12", regenerate:false}` | `WeeklyReviewRead` |
| POST | `/api/v1/reviews/weekly/{id}/reflections` | Lưu câu trả lời reflection | `{answer, flagged_transaction_ids}` | `ReflectionAnswerRead`, review `status="completed"` |
| GET | `/api/v1/reviews/weekly/pending` | Kiểm tra banner Thứ Hai | — | `{has_pending:true, week_start:"2026-10-05"}` |

`regenerate=true` chỉ cho phép khi user bấm nút "Tạo lại"; giữ cùng `week_start`, ghi đè narrative/metrics mới và reset `status="generated"`, không xoá reflection cũ nếu đã có (trả cảnh báo UI trước khi regenerate).

### 4.3 AI

Model đọc từ env: `OPENAI_MODEL_SMART` cho review narrative, `OPENAI_MODEL_FAST` chỉ dùng nếu cần validate/repair rất ngắn; không hard-code `gpt-4o`.

```python
from typing import Literal
from pydantic import BaseModel, Field

class ReviewNarrative(BaseModel):
    observation: str = Field(description="What happened, có số liệu từ metrics")
    explanation: str = Field(description="Why, nguyên nhân dựa trên highlights")
    notice: list[str] = Field(min_length=1, max_length=3)
    action: str | None = Field(description="Gợi ý có điều kiện, không ra lệnh")
    reflection_question: str
    tone: Literal["neutral", "supportive"]
```

Prompt outline:
- System: bạn là Personal CFO tiếng Việt, viết trung lập, không phán xét.
- Input: `period=week`, `week_start`, metrics JSON, highlights JSON, danh sách allowed numbers.
- Output: đúng `ReviewNarrative`; mọi con số phải copy từ metrics/highlights; không tự cộng/trừ.
- Bắt buộc 3 tầng: Observation → Explanation → Action.

Guardrails:
- Cấm cụm: "bạn tiêu quá nhiều", "lãng phí", "bạn phải", "bạn nên ngay lập tức", "vô trách nhiệm", "phung phí".
- Narrative có số nào thì số đó phải tồn tại trong metrics/highlights (bao gồm `18%`, `620000`, `4`).
- Action dùng "nếu bạn muốn...", "bạn có thể cân nhắc...", không dùng mệnh lệnh.

### 4.4 Frontend

- Route `/reviews/weekly/[week]`, ví dụ `/reviews/weekly/2026-10-12`.
- Components: `WeeklyReviewPage`, `ReviewNarrative`, `ReviewMetricCards`, `HighlightList`, `ReflectionForm`, `FlagTransactionPicker`.
- Trang chủ: `PendingWeeklyReviewBanner` vào Thứ Hai, gọi `/reviews/weekly/pending`, link tới tuần trước.
- UI state:
  - Nếu chưa có review: nút "Tạo review tuần này".
  - Nếu AI lỗi nhưng fallback có: hiển thị badge "Bản tóm tắt tự động".
  - Reflection cho phép tick nhiều giao dịch và label "không đáng tiền".

## 5. Task breakdown

- [ ] T1 Migration + ORM/Pydantic schemas cho `weekly_reviews`, `reflection_answers`
- [ ] T2 `analytics_service.get_review_metrics(period="week")` với income, expense, breakdown, change % vs previous week
- [ ] T3 `detect_highlights` weekly: top categories, repeated clusters, top transactions
- [ ] T4 Implement `agents/review_graph.py` generic `period=week|month` với retry ≤2 và fallback
- [ ] T5 Router `/api/v1/reviews/weekly*` + regenerate + pending banner endpoint
- [ ] T6 Unit/API tests cho metrics, persist, reflection, regenerate
- [ ] T7 Golden AI tests `@pytest.mark.ai` cho seed tuần 2 có food +18%
- [ ] T8 Frontend route `/reviews/weekly/[week]` + components narrative/metrics/reflection
- [ ] T9 Home pending-review banner Thứ Hai, không scheduler
- [ ] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-06: weekly review engine`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```powershell
cd backend
alembic upgrade head
ruff check .
pytest tests\unit\test_review_metrics.py tests\api\test_weekly_reviews.py
pytest -m ai tests\ai_golden\test_weekly_review.py

cd ..\frontend
npm run gen:api
npm run lint
npm run dev
```

**Test cases (pytest deterministic)**
| # | Input / dữ liệu seed | Kỳ vọng |
|---|---|---|
| 1 | Tuần 2026-10-05: income 0, expense 1.900.000; tuần 2026-10-12: expense 2.242.000 | `expense_change_pct = 18` |
| 2 | Tuần 2 food 1.180.000, tuần 1 food 1.000.000 | highlight category `food`, `change_pct = 18` |
| 3 | Tuần 2: 4 giao dịch Ăn uống buổi tối 120.000, 150.000, 180.000, 170.000 | repeated cluster "4 lần ăn tối", `total = 620000` |
| 4 | Breakdown tuần 2: essential 1.420.000, non_essential 672.000, irregular 150.000 | JSON metrics đúng 3 số |
| 5 | POST reflection với transaction ngoài tuần | 422, không lưu answer |
| 6 | POST weekly review lần 2 `regenerate=false` | trả review cũ, không gọi graph |
| 7 | Validate narrative chứa số 999.000 không có trong metrics | fail validation, retry/fallback |

**Golden set AI (`@pytest.mark.ai`)**
| # | Metrics / highlights | Automatic checks |
|---|---|---|
| 1 | Week 2 expense 2.242.000, +18%, food +18%, 4 lần ăn tối tổng 620.000 | Có nhắc `18%`, `Ăn uống`/`food`, `4`, `620.000`; mọi số thuộc metrics |
| 2 | AI thử dùng "bạn tiêu quá nhiều" | Test banned phrases fail |
| 3 | Không có OpenAI key | `pytest` thường skip marker `ai`; endpoint dùng fallback khi mock AI lỗi |

**Kịch bản thao tác UI**
1. Mở `/reviews/weekly/2026-10-12` khi chưa có review → bấm "Tạo review" → thấy 4 phần What happened / Why / What to notice / Reflection.
2. Tick 2 giao dịch đặt đồ ăn, nhập "Không đáng tiền vì đặt lúc muộn" → lưu thành công, review chuyển `completed`.
3. Vào trang chủ vào Thứ Hai 2026-10-19 → thấy banner review tuần 2026-10-12 nếu chưa completed.
4. Bấm "Tạo lại" → có confirm, narrative cập nhật, không tự chạy nền.

## 7. Definition of Done

- [ ] Tất cả task mục 5 xong, verify mục 6 pass
- [ ] `pytest` không cần API key xanh; `pytest -m ai` xanh khi có key
- [ ] Narrative luôn qua validate số liệu + banned phrases hoặc dùng fallback
- [ ] Frontend không tính tiền/%; chỉ render số từ API
- [ ] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [ ] Commit `phase-06: ...`

## 8. Rủi ro / câu hỏi mở

- Lặp cụm "ăn tối" cần heuristic chuẩn hoá note tiếng Việt; Phase 6 chỉ cần rule đơn giản theo category + keyword/time bucket, không làm NLP sâu.
- Nếu OpenAI trả văn hay nhưng thêm số mới, validate phải ưu tiên an toàn và fallback.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:**
- **Đã làm:**
- **Lệch so với plan (và lý do):**
- **Nợ kỹ thuật / TODO để lại:**
- **Lệnh hữu ích:**
- **Gợi ý cho phase tiếp theo:**
