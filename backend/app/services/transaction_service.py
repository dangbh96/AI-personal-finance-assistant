"""Nghiệp vụ giao dịch: validate direction ↔ category.kind ↔ spending_type và tổng hợp (ADR-005)."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import Category, Transaction
from app.models.enums import SPENDING_TYPES
from app.repositories import category_repository, transaction_repository
from app.repositories.transaction_repository import TransactionFilters
from app.schemas.transaction import (
    CategoryTotal,
    SpendingTypeTotals,
    TransactionCreate,
    TransactionSummary,
    TransactionUpdate,
)

__all__ = [
    "TransactionFilters",
    "create_transaction",
    "delete_transaction",
    "delete_transactions_in_range",
    "get_transaction",
    "list_transactions",
    "summarize",
    "update_transaction",
    "validate_filters",
]


def validate_filters(filters: TransactionFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")


def _resolve_category(
    db: Session, category_id: uuid.UUID, direction: str, *, allow_archived: bool = False
) -> Category:
    category = category_repository.get(db, category_id)
    if category is None:
        raise DomainError("Danh mục không tồn tại", "category_not_found")
    if category.kind != direction:
        raise DomainError(
            f"Danh mục '{category.name}' dành cho "
            f"{'thu nhập' if category.kind == 'income' else 'chi tiêu'}, không khớp giao dịch",
            "category_kind_mismatch",
        )
    if category.is_archived and not allow_archived:
        raise DomainError(f"Danh mục '{category.name}' đã bị ẩn", "category_archived")
    return category


def _resolve_spending_type(
    direction: str, spending_type: str | None, category: Category
) -> str | None:
    if direction == "income":
        if spending_type is not None:
            raise DomainError(
                "Thu nhập không có loại chi tiêu (spending_type phải null)", "income_spending_type"
            )
        return None
    resolved = spending_type or category.default_spending_type
    if resolved is None:
        raise DomainError("Cần chọn loại chi tiêu cho khoản chi", "spending_type_required")
    return resolved


def get_transaction(db: Session, transaction_id: uuid.UUID) -> Transaction:
    transaction = transaction_repository.get(db, transaction_id)
    if transaction is None:
        raise NotFoundError("Không tìm thấy giao dịch", "transaction_not_found")
    return transaction


def list_transactions(
    db: Session, filters: TransactionFilters, *, page: int, page_size: int
) -> tuple[list[Transaction], int]:
    validate_filters(filters)
    return transaction_repository.list_transactions(
        db, filters, offset=(page - 1) * page_size, limit=page_size
    )


def create_transaction(db: Session, data: TransactionCreate) -> Transaction:
    category = _resolve_category(db, data.category_id, data.direction)
    transaction = Transaction(
        direction=data.direction,
        amount=data.amount,
        occurred_on=data.occurred_on,
        note=data.note,
        category=category,
        spending_type=_resolve_spending_type(data.direction, data.spending_type, category),
        source=data.source,
        raw_input=data.raw_input,
        ai_suggestion=data.ai_suggestion,
    )
    transaction_repository.add(db, transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def update_transaction(
    db: Session, transaction_id: uuid.UUID, data: TransactionUpdate
) -> Transaction:
    transaction = get_transaction(db, transaction_id)
    changes = data.model_dump(exclude_unset=True)

    direction = changes.get("direction", transaction.direction)
    category_id = changes.get("category_id", transaction.category_id)
    category_changed = category_id != transaction.category_id
    # Giữ được giao dịch cũ thuộc danh mục đã ẩn, nhưng không cho chuyển sang danh mục đã ẩn.
    category = _resolve_category(db, category_id, direction, allow_archived=not category_changed)

    if "spending_type" in changes:
        spending_type = changes["spending_type"]
    elif direction == "expense" and transaction.direction == "expense" and not category_changed:
        spending_type = transaction.spending_type
    else:
        spending_type = None  # → lấy default của category (expense) / null (income)

    transaction.direction = direction
    transaction.category = category
    transaction.spending_type = _resolve_spending_type(direction, spending_type, category)
    for field in ("amount", "occurred_on", "note"):
        if field in changes:
            setattr(transaction, field, changes[field])

    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction_id: uuid.UUID) -> None:
    transaction_repository.delete(db, get_transaction(db, transaction_id))
    db.commit()


def delete_transactions_in_range(db: Session, date_from: date, date_to: date) -> int:
    validate_filters(TransactionFilters(date_from=date_from, date_to=date_to))
    deleted = transaction_repository.delete_in_range(db, date_from, date_to)
    db.commit()
    return deleted


def summarize(db: Session, filters: TransactionFilters) -> TransactionSummary:
    validate_filters(filters)
    income_total = 0
    expense_total = 0
    by_spending_type = dict.fromkeys(SPENDING_TYPES, 0)
    for (
        direction,
        spending_type,
        total,
    ) in transaction_repository.totals_by_direction_and_spending_type(db, filters):
        if direction == "income":
            income_total += total
        else:
            expense_total += total
            if spending_type is not None:
                by_spending_type[spending_type] += total

    return TransactionSummary(
        date_from=filters.date_from,
        date_to=filters.date_to,
        income_total=income_total,
        expense_total=expense_total,
        net=income_total - expense_total,
        by_spending_type=SpendingTypeTotals(**by_spending_type),
        by_category=[
            CategoryTotal(category_id=cid, name=name, kind=kind, icon=icon, total=total)
            for cid, name, kind, icon, total in transaction_repository.totals_by_category(
                db, filters
            )
        ],
    )
