"""LangGraph review workflow (ADR-006) — dùng chung cho `period = week | month`.

    collect_metrics → detect_highlights → write_narrative ⇄ validate → persist
                                               ↘ (AI lỗi / fail sau 2 lần retry) fallback ↗

- `collect_metrics`, `detect_highlights`, `validate`, `fallback` là deterministic (services).
  Kỳ `month`: `collect_metrics` gom thêm budget vs actual + nhìn lại các review tuần trong tháng,
  `detect_highlights` dựng `MonthlyReviewMetrics` (tiết kiệm, tỉ trọng, khoản bất thường…).
- `write_narrative` gọi OpenAI (model smart) qua `ai/review_writer` (prompt theo kỳ); output không
  qua kiểm tra (số ngoài metrics, cụm từ cấm, thiếu tầng) → gửi lỗi cho model viết lại, tối đa
  `MAX_RETRIES`.
- AI chưa cấu hình / lỗi mạng → bỏ qua retry, dùng template dự phòng (`fallback_used = true`).
- `persist` lưu theo kỳ: `week` → `weekly_reviews`, `month` → `monthly_reviews`.
"""

import logging
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.ai import review_writer
from app.ai.openai_client import AIUnavailable, Message
from app.core.errors import DomainError
from app.models import MonthlyReview, WeeklyReview
from app.models.enums import ReviewPeriod
from app.schemas.review import (
    MonthlyBudgetSummary,
    PeriodMetrics,
    ReviewMetrics,
    ReviewNarrative,
    ReviewNarrativeOutput,
    WeeklyReflectionDigest,
)
from app.services import analytics_service, review_metrics, review_narrative, review_service
from app.services.review_metrics import TxRow

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
VALIDATION_FAILED = "validation_failed"

Writer = Callable[[list[Message]], tuple[ReviewNarrativeOutput, str]]
Persister = Callable[[Session, date, ReviewMetrics, ReviewNarrative, str | None], Any]


class ReviewState(TypedDict, total=False):
    period: ReviewPeriod
    period_start: date
    today: date
    metrics: PeriodMetrics
    transactions: list[TxRow]
    budget: MonthlyBudgetSummary | None
    reflections: list[WeeklyReflectionDigest]
    review_metrics: ReviewMetrics
    allowed: set[Decimal]
    messages: list[Message]
    draft: ReviewNarrativeOutput | None
    model: str | None
    attempts: int
    problems: list[str]
    ai_error: str | None
    narrative: ReviewNarrative
    review: Any


PERSISTERS: dict[str, Persister] = {
    "week": review_service.save_weekly_review,
    "month": review_service.save_monthly_review,
}


def build_review_graph(db: Session, *, writer: Writer | None = None):
    """Compile graph cho 1 request (db session đóng gói trong node, không nằm trong state)."""
    write = writer or review_writer.write_narrative

    def collect_metrics(state: ReviewState) -> ReviewState:
        data = analytics_service.get_review_metrics(
            db, state["period"], state["period_start"], state["today"]
        )
        return {
            "metrics": data.metrics,
            "transactions": data.transactions,
            "budget": data.budget,
            "reflections": data.reflections,
        }

    def detect_highlights(state: ReviewState) -> ReviewState:
        metrics = review_metrics.build_review_metrics(
            state["metrics"],
            state["transactions"],
            budget=state.get("budget"),
            reflections=state.get("reflections", []),
        )
        return {
            "review_metrics": metrics,
            "allowed": review_narrative.allowed_numbers(metrics),
            "messages": review_writer.build_messages(metrics),
            "attempts": 0,
            "problems": [],
            "ai_error": None,
        }

    def write_narrative(state: ReviewState) -> ReviewState:
        attempts = state["attempts"] + 1
        try:
            draft, model = write(state["messages"])
        except AIUnavailable as exc:
            logger.warning("review_graph ai_error=%s attempt=%d", exc.code, attempts)
            return {"attempts": attempts, "draft": None, "ai_error": exc.code}
        return {"attempts": attempts, "draft": draft, "model": model}

    def validate(state: ReviewState) -> ReviewState:
        draft = state["draft"]
        assert draft is not None
        problems = review_narrative.validate_narrative(
            draft, state["review_metrics"], state["allowed"]
        )
        if not problems:
            return {
                "problems": [],
                "narrative": ReviewNarrative(**draft.model_dump(), fallback_used=False),
            }
        logger.warning(
            "review_graph invalid_narrative attempt=%d problems=%s", state["attempts"], problems
        )
        messages = [
            *state["messages"],
            {"role": "assistant", "content": draft.model_dump_json()},
            review_writer.feedback_message(problems),
        ]
        return {"problems": problems, "messages": messages}

    def fallback(state: ReviewState) -> ReviewState:
        reason = state.get("ai_error") or VALIDATION_FAILED
        return {
            "narrative": review_narrative.fallback_narrative(state["review_metrics"], reason),
            "model": review_narrative.FALLBACK_MODEL,
        }

    def persist(state: ReviewState) -> ReviewState:
        persister = PERSISTERS.get(state["period"])
        if persister is None:
            raise DomainError(
                f"Chưa hỗ trợ lưu review kỳ {state['period']}", "review_not_supported"
            )
        review = persister(
            db,
            state["period_start"],
            state["review_metrics"],
            state["narrative"],
            state.get("model"),
        )
        return {"review": review}

    def after_write(state: ReviewState) -> str:
        return "fallback" if state.get("ai_error") else "validate"

    def after_validate(state: ReviewState) -> str:
        if not state["problems"]:
            return "persist"
        return "write_narrative" if state["attempts"] <= MAX_RETRIES else "fallback"

    graph = StateGraph(ReviewState)
    graph.add_node("collect_metrics", collect_metrics)
    graph.add_node("detect_highlights", detect_highlights)
    graph.add_node("write_narrative", write_narrative)
    graph.add_node("validate", validate)
    graph.add_node("fallback", fallback)
    graph.add_node("persist", persist)
    graph.add_edge(START, "collect_metrics")
    graph.add_edge("collect_metrics", "detect_highlights")
    graph.add_edge("detect_highlights", "write_narrative")
    graph.add_conditional_edges("write_narrative", after_write, ["validate", "fallback"])
    graph.add_conditional_edges(
        "validate", after_validate, ["persist", "write_narrative", "fallback"]
    )
    graph.add_edge("fallback", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def run_review(
    db: Session,
    period: ReviewPeriod,
    period_start: date,
    today: date,
    *,
    writer: Writer | None = None,
) -> ReviewState:
    graph = build_review_graph(db, writer=writer)
    state: ReviewState = {"period": period, "period_start": period_start, "today": today}
    result: ReviewState = graph.invoke(state)  # type: ignore[assignment]
    logger.info(
        "review_graph period=%s start=%s attempts=%s model=%s fallback=%s",
        period,
        period_start,
        result.get("attempts"),
        result.get("model"),
        result["narrative"].fallback_used,
    )
    return result


def get_or_generate_weekly_review(
    db: Session, week_start: date, *, today: date, regenerate: bool = False
) -> WeeklyReview:
    """Review đã có → trả luôn (không chạy graph), trừ khi `regenerate`."""
    review_service.ensure_week_started(week_start, today)
    existing = review_service.get_weekly_by_week(db, week_start)
    if existing is not None and not regenerate:
        return existing
    return run_review(db, "week", week_start, today)["review"]


def get_or_generate_monthly_review(
    db: Session, month: date, *, today: date, regenerate: bool = False
) -> MonthlyReview:
    """Như `get_or_generate_weekly_review` cho tháng (`month` = ngày 1)."""
    review_service.ensure_month_started(month, today)
    existing = review_service.get_monthly_by_month(db, month)
    if existing is not None and not regenerate:
        return existing
    return run_review(db, "month", month, today)["review"]
