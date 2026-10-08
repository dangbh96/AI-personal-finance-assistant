"""Giá trị enum dùng chung (tên theo docs/product/glossary.md).

Lưu trong DB dạng TEXT + CHECK constraint; `Literal` giúp Pydantic/OpenAPI sinh enum cho frontend.
"""

from typing import Literal, get_args

Direction = Literal["income", "expense"]
SpendingType = Literal["essential", "non_essential", "irregular"]
TransactionSource = Literal["manual", "nl", "receipt", "import", "recurring"]

DIRECTIONS: tuple[str, ...] = get_args(Direction)
SPENDING_TYPES: tuple[str, ...] = get_args(SpendingType)
TRANSACTION_SOURCES: tuple[str, ...] = get_args(TransactionSource)


def sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)
