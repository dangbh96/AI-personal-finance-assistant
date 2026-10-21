"""Schema Flexible budget zones (Phase 9). Tiền là số nguyên đồng (ADR-007).

Mọi ngưỡng và trạng thái vùng do `services/zone_service` tính (deterministic, ADR-005) — frontend
chỉ hiển thị.
"""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ZoneMode, ZoneStatus
from app.schemas.budget import Money

AutoZoneBasis = Literal["history", "fallback"]
AutoZoneFallbackReason = Literal["insufficient_history", "irregular_group"]


class ZoneUpdate(BaseModel):
    """`manual` → bắt buộc đủ 3 ngưỡng, `comfort_low <= comfort_high <= warning_threshold`.
    `auto` → không gửi ngưỡng; backend tính lại ngay từ lịch sử (hoặc % dự phòng)."""

    model_config = ConfigDict(extra="forbid")

    zone_mode: ZoneMode
    comfort_low: Money | None = None
    comfort_high: Money | None = None
    warning_threshold: Money | None = None


class ZoneRecalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allocation_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="null = mọi dòng auto (trừ nhóm savings); dòng manual được bỏ qua",
    )


class ZoneThresholdsRead(BaseModel):
    comfort_low: int
    comfort_high: int
    warning_threshold: int


class AllocationZoneRead(BaseModel):
    """Vùng của một dòng phân bổ trong tháng (gắn vào Budget vs Actual)."""

    zone_mode: ZoneMode
    comfort_low: int | None
    comfort_high: int | None
    warning_threshold: int | None
    calculated: bool = Field(
        description="false nếu dòng auto chưa được tính vùng (ngưỡng null, zone null)"
    )
    zone: ZoneStatus | None = Field(
        description="normal: actual <= comfort_high · attention: <= warning_threshold · "
        "review_needed: > warning_threshold"
    )
    early_warning: bool = Field(
        description="Tháng đang chạy và % đã dùng vượt % tháng đã qua hơn 10 điểm % (pro-rata); "
        "không đổi `zone`"
    )
    early_warning_message: str | None


class ZoneHistoryMonthRead(BaseModel):
    month: date
    actual: int = Field(description="Chi trong phạm vi dòng, KHÔNG tính giao dịch irregular")
    irregular_excluded: int = Field(description="Tổng giao dịch irregular đã loại ra")
    transaction_count: int
    has_data: bool = Field(description="Tháng có ít nhất 1 giao dịch chi trong phạm vi")
    used: bool = Field(description="Tháng được dùng để tính mean / std")


class AutoZoneDetailRead(BaseModel):
    """Cách auto mode tính ngưỡng (tính lại khi đọc, để giải thích và phát hiện ngưỡng cũ)."""

    basis: AutoZoneBasis = Field(
        description="history: >= 3 tháng dữ liệu · fallback: % cố định theo planned"
    )
    fallback_reason: AutoZoneFallbackReason | None
    min_history_months: int
    max_history_months: int
    history_months: int = Field(description="Số tháng có dữ liệu được dùng")
    history: list[ZoneHistoryMonthRead] = Field(
        description="Các tháng trước tháng ngân sách (tối đa max_history_months), cũ nhất trước"
    )
    mean: int | None = Field(description="Trung bình (làm tròn tới đồng) — chỉ khi basis=history")
    std: int | None = Field(description="Độ lệch chuẩn tổng thể (làm tròn tới đồng)")
    suggested: ZoneThresholdsRead = Field(description="Ngưỡng auto tính từ dữ liệu hiện tại")
    stale: bool = Field(description="Ngưỡng đã lưu khác ngưỡng tính từ dữ liệu hiện tại")


class ZoneEvidence(BaseModel):
    """Vùng của dòng trong tháng advisor xét (phase-09 § 4.3) — chỉ để AI trích số đã tính."""

    zone_mode: ZoneMode
    planned_amount: int
    comfort_low: int
    comfort_high: int
    warning_threshold: int
    actual_amount: int
    zone: ZoneStatus
    early_warning: bool
