from sqlalchemy import Boolean, CheckConstraint, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import DIRECTIONS, SPENDING_TYPES, sql_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(f"kind IN ({sql_in(DIRECTIONS)})", name="kind"),
        CheckConstraint(
            f"default_spending_type IS NULL OR default_spending_type IN ({sql_in(SPENDING_TYPES)})",
            name="default_spending_type",
        ),
        CheckConstraint(
            "kind = 'expense' OR default_spending_type IS NULL",
            name="income_no_spending_type",
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    default_spending_type: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
