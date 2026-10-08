import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import Category


def get(db: Session, category_id: uuid.UUID) -> Category | None:
    return db.get(Category, category_id)


def get_by_slug(db: Session, slug: str) -> Category | None:
    return db.scalar(select(Category).where(Category.slug == slug))


def list_categories(
    db: Session, *, kind: str | None = None, include_archived: bool = False
) -> list[Category]:
    stmt = select(Category)
    if kind is not None:
        stmt = stmt.where(Category.kind == kind)
    if not include_archived:
        stmt = stmt.where(Category.is_archived.is_(False))
    stmt = stmt.order_by(Category.kind.desc(), Category.is_system.desc(), Category.name)
    return list(db.scalars(stmt))


def slug_exists(db: Session, slug: str) -> bool:
    return bool(db.scalar(select(exists().where(Category.slug == slug))))


def add(db: Session, category: Category) -> Category:
    db.add(category)
    db.flush()
    return category
