"""Giá trị enum dùng chung (tên theo docs/product/glossary.md).

Lưu trong DB dạng TEXT + CHECK constraint; `Literal` giúp Pydantic/OpenAPI sinh enum cho frontend.
"""

from typing import Literal, get_args

Direction = Literal["income", "expense"]
SpendingType = Literal["essential", "non_essential", "irregular"]
TransactionSource = Literal["manual", "nl", "receipt", "import", "recurring"]
BudgetStrategy = Literal["envelope", "fifty_thirty_twenty", "pyf"]
BudgetStatus = Literal["draft", "active", "closed"]
AllocationGroup = Literal["essential", "wants", "savings", "irregular"]
ReviewPeriod = Literal["week", "month"]
ReviewStatus = Literal["generated", "completed"]
ReviewKind = Literal["weekly", "monthly"]
AdviceVerdict = Literal["adjust_budget", "adjust_behavior", "one_off", "on_track"]
AdviceStatus = Literal["open", "accepted", "dismissed"]
ZoneMode = Literal["manual", "auto"]
ZoneStatus = Literal["normal", "attention", "review_needed"]

DIRECTIONS: tuple[str, ...] = get_args(Direction)
SPENDING_TYPES: tuple[str, ...] = get_args(SpendingType)
TRANSACTION_SOURCES: tuple[str, ...] = get_args(TransactionSource)
BUDGET_STRATEGIES: tuple[str, ...] = get_args(BudgetStrategy)
BUDGET_STATUSES: tuple[str, ...] = get_args(BudgetStatus)
ALLOCATION_GROUPS: tuple[str, ...] = get_args(AllocationGroup)
REVIEW_STATUSES: tuple[str, ...] = get_args(ReviewStatus)
REVIEW_KINDS: tuple[str, ...] = get_args(ReviewKind)
ADVICE_VERDICTS: tuple[str, ...] = get_args(AdviceVerdict)
ADVICE_STATUSES: tuple[str, ...] = get_args(AdviceStatus)
ZONE_MODES: tuple[str, ...] = get_args(ZoneMode)


def sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)
