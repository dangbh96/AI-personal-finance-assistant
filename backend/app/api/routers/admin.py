from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.schemas.admin import AIUsageGroupBy, AIUsageReport, SmokeReport
from app.schemas.common import ErrorResponse
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

Today = Annotated[date | None, Query(description="Hôm nay (mặc định của server) — demo / test")]


@router.get("/ai-usage", response_model=AIUsageReport, responses={422: {"model": ErrorResponse}})
def ai_usage(
    db: DbSession,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    group_by: AIUsageGroupBy = "model",
    today: Today = None,
):
    """Token / chi phí ước tính / latency / lỗi của các lời gọi OpenAI (mặc định 30 ngày gần
    nhất), nhóm theo model / tác vụ / loại lời gọi. App local một người dùng (ADR-004) nên không
    có xác thực."""
    return admin_service.ai_usage_report(
        db,
        today=today or date.today(),
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
    )


@router.get("/smoke-data", response_model=SmokeReport)
def smoke_data(db: DbSession, today: Today = None):
    """(Dev) Dữ liệu đã đủ để chạy demo end-to-end chưa — danh mục, giao dịch, ngân sách, mục
    tiêu, khoản định kỳ, embedding, kiến thức, khoá AI."""
    return admin_service.smoke_check(db, today or date.today())
