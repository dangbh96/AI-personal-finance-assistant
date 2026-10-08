import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import Direction, SpendingType

CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
CategoryIcon = Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)]


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CategoryName
    kind: Direction
    default_spending_type: SpendingType | None = Field(
        default=None, description="Bắt buộc với kind=expense, phải null với kind=income"
    )
    icon: CategoryIcon | None = None

    @model_validator(mode="after")
    def _check_spending_type(self) -> "CategoryCreate":
        if self.kind == "income" and self.default_spending_type is not None:
            raise ValueError("Danh mục thu nhập không có loại chi tiêu mặc định")
        if self.kind == "expense" and self.default_spending_type is None:
            raise ValueError("Danh mục chi tiêu cần loại chi tiêu mặc định")
        return self


class CategoryUpdate(BaseModel):
    """PATCH: chỉ field được gửi mới được cập nhật. `kind`, `slug`, `is_system` không sửa được."""

    model_config = ConfigDict(extra="forbid")

    # Không nhận null cho name/is_archived (mặc định None chỉ để biểu thị "không gửi").
    name: CategoryName = None  # type: ignore[assignment]
    icon: CategoryIcon | None = None
    default_spending_type: SpendingType | None = None
    is_archived: bool = None  # type: ignore[assignment]


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    kind: Direction
    icon: str | None


class CategoryRead(CategoryBrief):
    default_spending_type: SpendingType | None
    is_system: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
