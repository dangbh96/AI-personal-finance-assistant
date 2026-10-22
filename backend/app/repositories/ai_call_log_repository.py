"""Tổng hợp `ai_call_logs` (Phase 18)."""

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import AICallLog


def aggregate(
    db: Session, date_from: datetime, date_to: datetime, group_by: str
) -> list[tuple[str, int, int, int, int, int, int]]:
    """`(key, calls, input_tokens, output_tokens, cost_vnd, latency_avg_ms, errors)` trong
    `[date_from, date_to)`."""
    column = {"model": AICallLog.model, "task": AICallLog.task, "kind": AICallLog.kind}[group_by]
    stmt = (
        select(
            column,
            func.count(),
            func.coalesce(func.sum(AICallLog.input_tokens), 0),
            func.coalesce(func.sum(AICallLog.output_tokens), 0),
            func.coalesce(func.sum(AICallLog.cost_estimate_vnd), 0),
            func.coalesce(func.avg(AICallLog.latency_ms), 0),
            func.coalesce(func.sum(case((AICallLog.status == "error", 1), else_=0)), 0),
        )
        .where(AICallLog.created_at >= date_from, AICallLog.created_at < date_to)
        .group_by(column)
    )
    return [
        (str(key), int(n), int(i), int(o), int(cost), round(float(lat)), int(err))
        for key, n, i, o, cost, lat, err in db.execute(stmt)
    ]
