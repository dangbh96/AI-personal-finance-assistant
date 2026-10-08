import uuid

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.text import slugify
from app.models import Category
from app.repositories import category_repository
from app.schemas.category import CategoryCreate, CategoryUpdate


def list_categories(
    db: Session, *, kind: str | None = None, include_archived: bool = False
) -> list[Category]:
    return category_repository.list_categories(db, kind=kind, include_archived=include_archived)


def get_category(db: Session, category_id: uuid.UUID) -> Category:
    category = category_repository.get(db, category_id)
    if category is None:
        raise NotFoundError("Không tìm thấy danh mục", "category_not_found")
    return category


def get_category_by_slug(db: Session, slug: str) -> Category:
    category = category_repository.get_by_slug(db, slug)
    if category is None:
        raise NotFoundError(f"Không tìm thấy danh mục '{slug}'", "category_not_found")
    return category


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name) or "category"
    slug, n = base, 2
    while category_repository.slug_exists(db, slug):
        slug, n = f"{base}_{n}", n + 1
    return slug


def create_category(db: Session, data: CategoryCreate) -> Category:
    category = Category(
        name=data.name,
        slug=_unique_slug(db, data.name),
        kind=data.kind,
        default_spending_type=data.default_spending_type,
        icon=data.icon,
        is_system=False,
    )
    category_repository.add(db, category)
    db.commit()
    db.refresh(category)
    return category


def update_category(db: Session, category_id: uuid.UUID, data: CategoryUpdate) -> Category:
    category = get_category(db, category_id)
    changes = data.model_dump(exclude_unset=True)
    if "default_spending_type" in changes:
        spending_type = changes["default_spending_type"]
        if category.kind == "income" and spending_type is not None:
            raise DomainError(
                "Danh mục thu nhập không có loại chi tiêu mặc định", "income_spending_type"
            )
        if category.kind == "expense" and spending_type is None:
            raise DomainError(
                "Danh mục chi tiêu cần loại chi tiêu mặc định", "spending_type_required"
            )
    for field, value in changes.items():
        setattr(category, field, value)
    db.commit()
    db.refresh(category)
    return category
