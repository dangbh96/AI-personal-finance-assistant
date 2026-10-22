"""Admin / vận hành (Phase 18): báo cáo token & chi phí AI, kiểm tra dữ liệu demo."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

AIUsageGroupBy = Literal["model", "task", "kind"]


class AIUsageRow(BaseModel):
    key: str = Field(description="Giá trị nhóm (tên model / tác vụ / loại lời gọi)")
    calls: int
    input_tokens: int
    output_tokens: int
    cost_estimate_vnd: int = Field(description="Chi phí ước tính (đồng) — model không có giá = 0")
    latency_ms_avg: int
    error_count: int


class AIUsageTotals(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cost_estimate_vnd: int
    error_count: int


class AIUsageReport(BaseModel):
    from_date: date
    to_date: date
    group_by: AIUsageGroupBy
    totals: AIUsageTotals
    rows: list[AIUsageRow] = Field(description="Chi phí cao nhất trước")
    note: str


class SmokeCheckResult(BaseModel):
    ok: bool
    area: str
    message: str
    required: bool = Field(description="false = khuyến nghị (demo vẫn chạy được)")


class SmokeReport(BaseModel):
    ok: bool = Field(description="Mọi kiểm tra bắt buộc đều đạt")
    missing: list[str] = Field(description="Khu vực chưa đạt")
    checks: list[SmokeCheckResult]
