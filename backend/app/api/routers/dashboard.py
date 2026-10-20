from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.schemas.analytics import MonthSummaryRead
from app.schemas.common import ErrorResponse
from app.services import analytics_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/month-summary", response_model=MonthSummaryRead, responses={422: {"model": ErrorResponse}}
)
def month_summary(
    db: DbSession,
    month: Annotated[
        date | None, Query(description="Một ngày trong tháng, mặc định tháng chứa `today`")
    ] = None,
    today: Annotated[
        date | None, Query(description="Ngày tính tiến độ tháng (mặc định hôm nay của server)")
    ] = None,
):
    """Thẻ tóm tắt tháng ở trang chủ: thu/chi/net thực tế (luôn có) và tiến độ ngân sách nếu
    tháng có ngân sách active/closed."""
    return analytics_service.get_month_summary(db, today or date.today(), month)
