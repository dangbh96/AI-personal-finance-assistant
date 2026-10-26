# Phase 06 — Weekly Review Engine

| | |
|---|---|
| **ID** | `phase-06-weekly-review` |
| **Trạng thái** | Done |
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

User có một trang review tuần theo format **What happened / Why / What to notice / Reflection**. App tự tổng hợp số liệu tuần, chỉ ra điểm đáng chú ý như "Ăn uống tăng 18%" hoặc "4 lần ăn tối, tổng 620.000", rồi hỏi user nhìn lại khoản nào "không đáng tiền". Đây là vòng lặp hành vi đầu tiên, biến ghi chép thành học hỏi.

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

- [x] T1 Migration + ORM/Pydantic schemas cho `weekly_reviews`, `reflection_answers`
- [x] T2 `analytics_service.get_review_metrics(period="week")` với income, expense, breakdown, change % vs previous week
- [x] T3 `detect_highlights` weekly: top categories, repeated clusters, top transactions
- [x] T4 Implement `agents/review_graph.py` generic `period=week|month` với retry ≤2 và fallback
- [x] T5 Router `/api/v1/reviews/weekly*` + regenerate + pending banner endpoint
- [x] T6 Unit/API tests cho metrics, persist, reflection, regenerate
- [x] T7 Golden AI tests `@pytest.mark.ai` cho seed tuần 2 có food +18%
- [x] T8 Frontend route `/reviews/weekly/[week]` + components narrative/metrics/reflection
- [x] T9 Home pending-review banner Thứ Hai, không scheduler
- [x] T10 Cập nhật docs/PROGRESS/handoff + commit `phase-06: weekly review engine`

## 6. Verify / Acceptance criteria

**Lệnh chạy**
```bash
cd backend
alembic upgrade head
ruff check .
pytest tests/unit/test_review_metrics.py tests/api/test_weekly_reviews.py
pytest -m ai tests/ai_golden/test_weekly_review.py

cd ../frontend
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

- [x] Tất cả task mục 5 xong, verify mục 6 pass
- [x] `pytest` không cần API key xanh; `pytest -m ai` xanh khi có key
- [x] Narrative luôn qua validate số liệu + banned phrases hoặc dùng fallback
- [x] Frontend không tính tiền/%; chỉ render số từ API
- [x] [PROGRESS.md](../PROGRESS.md) cập nhật, Handoff notes điền
- [x] Commit `phase-06: ...`

## 8. Rủi ro / câu hỏi mở

- Lặp cụm "ăn tối" cần heuristic chuẩn hoá note tiếng Việt; Phase 6 chỉ cần rule đơn giản theo category + keyword/time bucket, không làm NLP sâu.
- Nếu OpenAI trả văn hay nhưng thêm số mới, validate phải ưu tiên an toàn và fallback.

## 9. Handoff notes

> Điền khi kết thúc phase. Session sau sẽ đọc phần này đầu tiên.

- **Ngày hoàn thành:** 2026-10-21
- **Đã làm:**
  - **Migration** `20261020_63c5cd20a0e3_weekly_review`: `weekly_reviews` (UNIQUE `week_start`, CHECK Thứ Hai, `status generated|completed`), `reflection_answers` (CHECK `review_kind weekly|monthly`, index `(review_kind, review_id)`, không FK). ORM `models/review.py`; enum `ReviewPeriod/ReviewStatus/ReviewKind`.
  - **Dependency** `langgraph>=1.2,<1.3` (cài 1.2.16; ADR-006 yêu cầu pin).
  - **Deterministic (services, không import `ai`):**
    - `services/review_metrics.py` (hàm thuần): `period_range(week|month)`, `change_pct` (% nguyên, half-up, `None` khi kỳ trước = 0), `compute_period_metrics` (thu/chi/net, kỳ trước, breakdown spending_type 2 kỳ, `by_category` gồm cả danh mục chỉ có ở kỳ trước, tiến độ `days_elapsed/complete/as_of`), `time_bucket` (sáng/trưa/tối/đêm/khuya trong ghi chú), `repeated_clusters` (≥ 3 khoản cùng danh mục + cùng buổi, hoặc cùng `normalize_pattern(note)`; tối đa 3, tổng lớn trước), `top_transactions`, `detect_highlights`.
    - `analytics_service.get_review_metrics(db, period, start, today)` → `ReviewData(metrics, transactions)`; repo `transaction_repository.list_between`, `get_many`.
    - `services/review_narrative.py`: `extract_numbers` (đọc "1.180.000", "18%", "0,5 triệu", "620k", "2.5tr", ngày "12/10/2026"), `allowed_numbers(metrics)` (mọi số trong metrics trừ UUID, giá trị tuyệt đối, cả ngày/tháng/năm và độ dài danh sách), `validate_narrative` (số ⊆ allowed, cụm cấm so cả không dấu, đủ tầng, action có điều kiện), `fallback_narrative` (template, luôn qua validate — có test), `period_label`.
    - `services/review_service.py`: `save_weekly_review` (tạo / ghi đè khi regenerate, `status=generated`, giữ reflection), `add_weekly_reflection` (câu hỏi lấy từ narrative; flagged phải là khoản chi trong tuần; trùng id bị gộp; review → `completed`), `pending_weekly`, `to_read(s)`.
  - **AI:** `ai/review_writer.py` + prompt `review_narrative.v1.md` (metrics JSON bỏ UUID + danh sách số được phép), model `OPENAI_MODEL_SMART`, timeout 60s.
  - **LangGraph** `agents/review_graph.py`: `collect_metrics → detect_highlights → write_narrative ⇄ validate → persist`, nhánh `fallback`; retry ≤ 2 khi validate fail (gửi danh sách lỗi cho model); `AIUnavailable` → fallback ngay (không retry). `PERSISTERS` theo `period` (Phase 7 thêm `month`). `get_or_generate_weekly_review` không chạy graph nếu đã có review và `regenerate=false`. Writer inject được (test).
  - **API** `api/routers/reviews.py`: `GET /reviews/weekly?from&to`, `GET /reviews/weekly/pending?today`, `POST /reviews/weekly {week_start, regenerate, today}` (200), `GET /reviews/weekly/{week_start}` (404 `weekly_review_not_found`), `POST /reviews/weekly/{id}/reflections {answer, flagged_transaction_ids}` (201).
  - **Frontend:** route `/reviews/weekly` (`WeeklyReviewIndex`) và `/reviews/weekly/[week]` (`WeeklyReviewPage` → `ReviewMetricCards`, `ReviewNarrative` + badge "Bản tóm tắt tự động", `HighlightList`, `ReflectionForm` + `FlagTransactionPicker`; confirm "Tạo lại"; tuần trước/sau; `?today=`). Trang chủ: `PendingWeeklyReviewBanner`. Nav "Review" đã bật. `lib/dates`: `addDays`, `weekStartOf`, `isMonday`, `formatWeekRange`. `gen:api` đã chạy lại.
  - **Test:** 440 pass (+71): `tests/unit/test_review_metrics.py` (47: test case 1–4, 7 mục 6 + parse số, cụm từ cấm, action, fallback luôn hợp lệ), `tests/api/test_weekly_reviews.py` (24: generate với AI giả, test case 5–6, retry rồi thành công, fail 3 lần → fallback `validation_failed`, AI timeout → fallback không retry, regenerate giữ reflection, tuần chưa bắt đầu, list/get, reflection hợp lệ/ngoài tuần/thu nhập/rỗng, pending banner). Dữ liệu dùng chung `tests/review_dataset.py`.
  - **Golden AI** `tests/ai_golden/test_weekly_review.py` (`pytest -m ai`): **2/2 pass** với `gpt-4o` — lần gọi đầu qua validate (không fallback), có `18%`, Ăn uống, `4`, `620.000`; khi bị nhồi yêu cầu "bạn tiêu quá nhiều / lãng phí" vẫn ra văn trung lập.
  - **Verify:** `alembic upgrade head`, `ruff check`, `ruff format --check`, `pytest`, `pytest -m ai tests/ai_golden/test_weekly_review.py`, `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm run build` xanh. 4 kịch bản UI mục 6 chạy trên trình duyệt (DB dev): tạo review 12/10 (gpt-4o), tick 2 "Ăn tối nhà hàng" + câu trả lời → "Đã nhìn lại", banner ở `/?today=2026-10-12` (tuần 05/10) và không hiện ở `/?today=2026-10-19` sau khi completed, "Tạo lại" có confirm → "Chờ nhìn lại", nhìn lại cũ còn.
- **Lệch so với plan (và lý do):**
  - `metrics` lưu thêm `highlights` (cùng JSONB) để UI hiển thị evidence và validate số; thêm `previous_by_spending_type`, `by_category` (kèm `change_pct`), `expense_count`, tiến độ tuần (`days_elapsed`, `complete`, `as_of`) — review tuần đang chạy được phép (số liệu tính đến hôm nay), tuần tương lai → 422 `week_not_started`.
  - `% thay đổi` là **số nguyên** (half-up) để narrative viết "18%" khớp metrics; `null` khi kỳ trước = 0.
  - `narrative` thêm `fallback_reason` (mã lỗi AI hoặc `validation_failed`); `model = "fallback_template"` khi dùng bản tự động.
  - AI lỗi (chưa cấu hình / timeout / 5xx) đi thẳng fallback, chỉ retry khi output không qua kiểm tra — tránh 3 × timeout.
  - Validate thêm: thiếu `action` khi tuần có giao dịch; action phải có điều kiện ("nếu / có thể / cân nhắc / thử"); thêm "hoang phí" vào cụm cấm.
  - Reflection chỉ nhận khoản **chi** (thu nhập → 422 `flagged_transaction_not_expense`); cho phép chỉ tick giao dịch không cần câu trả lời, nhưng không được rỗng cả hai (`reflection_empty`). `POST /reviews/weekly` trả 200 (cả khi tạo mới lẫn trả review cũ).
  - `pending`: chỉ `has_pending` khi hôm nay là Thứ Hai **và tuần trước có giao dịch** và review chưa completed; trả thêm `review_id`, `review_status`.
  - Cụm lặp: "buổi trong ngày" lấy từ từ khoá trong ghi chú (giao dịch chỉ có ngày, không có giờ). Nhãn "Ăn uống buổi tối".
  - Quy tắc phụ thuộc: `agents` được gọi `services` và `ai` (writer) — cập nhật `backend-components.md`.
  - Layout: `AppNav` bọc `<Suspense>` (tách `AppNavLinks`) vì `usePathname()` là dữ liệu runtime ở route động đầu tiên (`/reviews/weekly/[week]`, Cache Components).
- **Nợ kỹ thuật / TODO để lại:**
  - `gpt-4o` đôi khi mất ~47s cho lần gọi đầu (lần sau ~4s); timeout 60s + SDK retry mạng 2 lần. Chưa có streaming / job nền — UI chỉ hiện "Đang tạo review…".
  - Allowed numbers là **tập giá trị** (không theo ngữ cảnh): model vẫn có thể gán sai một số có thật cho ý khác (vd % của danh mục này cho danh mục kia). Golden test chưa bắt lỗi này.
  - Heuristic buổi trong ngày chỉ dựa vào ghi chú; khi có giờ giao dịch (chưa có cột) nên dùng giờ thật.
  - Reflection chưa được dùng ngược lại (vd đưa "không đáng tiền" vào review tháng / Coach) — Phase 7/10.
  - Không có test tự động frontend (Phase 18). `weekly_reviews` UNIQUE `week_start` cần thêm `user_id` khi có auth.
- **Lệnh hữu ích:**
  - `(cd backend && pytest tests/unit/test_review_metrics.py tests/api/test_weekly_reviews.py -q)`
  - `(cd backend && pytest -m ai tests/ai_golden/test_weekly_review.py -s)`
  - `curl -s -X POST localhost:8000/api/v1/reviews/weekly -H "Content-Type: application/json" -d '{"week_start":"2026-10-12","today":"2026-10-20"}'`
  - `curl -s "localhost:8000/api/v1/reviews/weekly/pending?today=2026-10-19"`
  - UI: `/reviews/weekly/2026-10-12`, `/?today=2026-10-12` (banner).
- **Gợi ý cho phase tiếp theo (Phase 7 — Monthly review):**
  - Graph đã generic: `review_metrics.period_range("month", …)` + `compute_period_metrics` + `detect_highlights` chạy được cho tháng; chỉ cần bảng `monthly_reviews`, persister `"month"` trong `review_graph.PERSISTERS`, router và UI. `review_narrative.fallback_narrative` / `period_label` đã xử lý `month`.
  - Có thể gộp evidence budget (`analytics_service.get_budget_status`) vào metrics tháng — nhớ rằng mọi số đưa vào metrics sẽ thành "số được phép".
  - `reflection_answers` dùng lại với `review_kind = 'monthly'`; `review_service.to_reads` lọc theo kind.
  - DB dev hiện có review tuần 12/10/2026 (gpt-4o, đã regenerate, 1 câu trả lời nhìn lại).
