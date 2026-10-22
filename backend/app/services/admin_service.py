"""Vận hành (Phase 18) — báo cáo AI usage và kiểm tra dữ liệu demo. Chỉ đọc."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.repositories import (
    ai_call_log_repository,
    budget_repository,
    category_repository,
    embedding_repository,
    goal_repository,
    knowledge_repository,
    recurring_repository,
    transaction_repository,
)
from app.schemas.admin import (
    AIUsageGroupBy,
    AIUsageReport,
    AIUsageRow,
    AIUsageTotals,
    SmokeCheckResult,
    SmokeReport,
)
from app.services.money import add_months

DEFAULT_USAGE_DAYS = 30
MAX_USAGE_DAYS = 366


def ai_usage_report(
    db: Session,
    *,
    today: date,
    date_from: date | None = None,
    date_to: date | None = None,
    group_by: AIUsageGroupBy = "model",
) -> AIUsageReport:
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_USAGE_DAYS - 1)
    if date_from > date_to:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")
    if (date_to - date_from).days >= MAX_USAGE_DAYS:
        raise DomainError("Khoảng ngày tối đa 366 ngày", "range_too_long")
    start = datetime.combine(date_from, time.min, tzinfo=UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
    rows = [
        AIUsageRow(
            key=key,
            calls=calls,
            input_tokens=i,
            output_tokens=o,
            cost_estimate_vnd=cost,
            latency_ms_avg=lat,
            error_count=err,
        )
        for key, calls, i, o, cost, lat, err in ai_call_log_repository.aggregate(
            db, start, end, group_by
        )
    ]
    rows.sort(key=lambda r: (-r.cost_estimate_vnd, -r.calls, r.key))
    return AIUsageReport(
        from_date=date_from,
        to_date=date_to,
        group_by=group_by,
        totals=AIUsageTotals(
            calls=sum(r.calls for r in rows),
            input_tokens=sum(r.input_tokens for r in rows),
            output_tokens=sum(r.output_tokens for r in rows),
            cost_estimate_vnd=sum(r.cost_estimate_vnd for r in rows),
            error_count=sum(r.error_count for r in rows),
        ),
        rows=rows,
        note="Chi phí là ước tính theo bảng giá niêm yết × 26.000 đ/USD (ngày theo UTC), không "
        "phải hoá đơn OpenAI.",
    )


def smoke_check(db: Session, today: date) -> SmokeReport:
    """Dữ liệu đủ để chạy demo end-to-end chưa (docs/demo-script.md)."""
    checks: list[SmokeCheckResult] = []

    def add(area: str, ok: bool, message: str, required: bool = True) -> None:
        checks.append(SmokeCheckResult(ok=ok, area=area, message=message, required=required))

    categories = category_repository.list_categories(db)
    add("categories", len(categories) >= 10, f"{len(categories)} danh mục đang dùng")

    three_months_ago = add_months(today.replace(day=1), -3)
    totals = transaction_repository.totals_by_direction(db, three_months_ago, today)
    add(
        "transactions",
        bool(totals.get("income")) and bool(totals.get("expense")),
        "Có thu và chi trong 3 tháng gần nhất"
        if totals.get("income") and totals.get("expense")
        else "Thiếu thu hoặc chi trong 3 tháng gần nhất — chạy seed_demo",
    )

    budget = budget_repository.get_by_month(db, today.replace(day=1))
    add(
        "budget",
        budget is not None and budget.status in ("active", "closed"),
        f"Ngân sách tháng {today:%m/%Y}: {budget.status if budget else 'chưa có'}",
    )

    goals = goal_repository.list_goals(db, statuses=["active"])
    add("goals", bool(goals), f"{len(goals)} mục tiêu đang thực hiện", required=False)

    recurring = recurring_repository.list_recurring(db, active=True)
    add("recurring", bool(recurring), f"{len(recurring)} khoản định kỳ", required=False)

    missing = embedding_repository.count_missing(db)
    add(
        "embeddings",
        missing == 0,
        "Mọi giao dịch đã có embedding"
        if missing == 0
        else f"{missing} giao dịch chưa có embedding — chạy backfill_embeddings",
    )

    chunks = knowledge_repository.count_chunks(db)
    add(
        "knowledge",
        chunks > 0,
        f"{chunks} đoạn kiến thức" if chunks else "Chưa ingest kiến thức — chạy ingest_knowledge",
    )

    configured = bool((get_settings().openai_api_key or "").strip())
    add(
        "ai",
        configured,
        "Đã cấu hình OPENAI_API_KEY"
        if configured
        else "Chưa có OPENAI_API_KEY — tính năng AI trả 503",
        required=False,
    )

    failed = [c.area for c in checks if not c.ok]
    return SmokeReport(ok=all(c.ok for c in checks if c.required), missing=failed, checks=checks)
