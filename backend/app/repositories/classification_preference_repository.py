import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, ClassificationPreference


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get(db: Session, preference_id: uuid.UUID) -> ClassificationPreference | None:
    return db.get(ClassificationPreference, preference_id)


def get_by_pattern(db: Session, pattern: str) -> ClassificationPreference | None:
    return db.scalar(
        select(ClassificationPreference).where(
            ClassificationPreference.user_id.is_(None),
            ClassificationPreference.pattern == pattern,
        )
    )


def list_preferences(
    db: Session,
    *,
    q: str | None = None,
    q_pattern: str | None = None,
    category_id: uuid.UUID | None = None,
    active_only: bool = False,
    limit: int | None = None,
) -> list[ClassificationPreference]:
    """Mới dùng gần nhất trước. `q` tìm trong câu ví dụ, `q_pattern` (đã chuẩn hoá) trong
    pattern."""
    stmt = select(ClassificationPreference)
    conditions = []
    if q:
        conditions.append(
            ClassificationPreference.example_text.ilike(f"%{_escape_like(q)}%", escape="\\")
        )
    if q_pattern:
        conditions.append(
            ClassificationPreference.pattern.ilike(f"%{_escape_like(q_pattern)}%", escape="\\")
        )
    if conditions:
        stmt = stmt.where(or_(*conditions))
    if category_id is not None:
        stmt = stmt.where(ClassificationPreference.category_id == category_id)
    if active_only:
        stmt = stmt.join(ClassificationPreference.category).where(Category.is_archived.is_(False))
    stmt = stmt.order_by(
        ClassificationPreference.last_used_at.desc().nulls_last(),
        ClassificationPreference.updated_at.desc(),
        ClassificationPreference.pattern,
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).unique())


def add(db: Session, preference: ClassificationPreference) -> ClassificationPreference:
    db.add(preference)
    db.flush()
    return preference


def delete(db: Session, preference: ClassificationPreference) -> None:
    db.delete(preference)
    db.flush()
