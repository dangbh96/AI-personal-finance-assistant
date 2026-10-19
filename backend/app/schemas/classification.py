"""Schema cho classification preference (Phase 3)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import SpendingType
from app.schemas.category import CategoryBrief

PATTERN_MAX_LENGTH = 100


ExampleText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class PreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pattern: str = Field(description="Từ khoá đã chuẩn hoá (bỏ dấu, lowercase)")
    example_text: str
    category_id: uuid.UUID
    category: CategoryBrief
    spending_type: SpendingType | None
    hit_count: int = Field(description="Số lần user xác nhận cách phân loại này")
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PreferenceList(BaseModel):
    items: list[PreferenceRead]


class PreferenceCreate(BaseModel):
    """Preference user đã xác nhận (thường từ draft của `POST /classification-preferences/parse`).

    Trùng pattern thì cập nhật preference cũ.
    """

    model_config = ConfigDict(extra="forbid")

    pattern: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PATTERN_MAX_LENGTH)
    ]
    category_slug: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    spending_type: SpendingType | None = Field(
        default=None,
        description="Chỉ cho danh mục chi tiêu; bỏ trống thì dùng default_spending_type",
    )
    example_text: ExampleText | None = None


class PreferenceParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
