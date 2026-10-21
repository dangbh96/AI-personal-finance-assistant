from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.forecast import (
    CalendarMonth,
    ForecastOutput,
    ForecastSettings,
    ForecastSettingsUpdate,
)
from app.services import forecast_service

router = APIRouter(tags=["calendar-forecast"])

INVALID = {422: {"model": ErrorResponse}}

Today = Annotated[
    date | None,
    Query(description="Hôm nay phía user (mặc định của server) — dùng cho demo/test"),
]


def _today(today: date | None) -> date:
    return today or date.today()


@router.get("/calendar/month", response_model=CalendarMonth, responses=INVALID)
def get_calendar_month(
    db: DbSession,
    month: Annotated[
        date | None, Query(description="Ngày bất kỳ trong tháng; mặc định tháng này")
    ] = None,
    today: Today = None,
):
    """Sự kiện tiền trong tháng: 💰 thu, 🏠 nhà, 💳 thẻ, 📱 tiện ích, 🎯 để dành mục tiêu."""
    day = _today(today)
    return forecast_service.calendar_month(db, month or day, day)


@router.get("/forecast", response_model=ForecastOutput, responses=INVALID)
def get_forecast(
    db: DbSession,
    days: Annotated[
        int,
        Query(
            ge=forecast_service.MIN_FORECAST_DAYS,
            le=forecast_service.MAX_FORECAST_DAYS,
            description="Số ngày dự báo (UI dùng 30 / 60)",
        ),
    ] = 30,
    start_date: Annotated[date | None, Query(description="Mặc định hôm nay")] = None,
    today: Today = None,
):
    """Dự báo số dư từng ngày (deterministic). `starting_balance` là số user tự nhập."""
    return forecast_service.build_forecast(db, start_date or _today(today), days)


@router.get("/settings/forecast", response_model=ForecastSettings)
def get_forecast_settings(db: DbSession):
    return forecast_service.get_settings(db)


@router.patch("/settings/forecast", response_model=ForecastSettings, responses=INVALID)
def update_forecast_settings(db: DbSession, data: ForecastSettingsUpdate, today: Today = None):
    """Sửa số dư đầu (giả định của forecast), ngưỡng cảnh báo, ngày để dành mục tiêu."""
    return forecast_service.update_settings(db, data, _today(today))
