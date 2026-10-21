"""Dữ liệu cố định cho test Budget advisor (phase-08 § 6 — 4 test case chuẩn).

| Danh mục | Planned 10/2026 | 08/2026   | 09/2026   | 10/2026   | Verdict mong đợi              |
|----------|-----------------|-----------|-----------|-----------|-------------------------------|
| Ăn uống  | 4.000.000       | 4.400.000 | 4.600.000 | 4.500.000 | adjust_budget → 4.500.000     |
| Mua sắm  | 2.000.000       | 1.500.000 | 1.500.000 | 8.000.000 | one_off (Laptop 6.500.000)    |
| Giải trí | 1.000.000       |   800.000 | 1.600.000 | 1.400.000 | adjust_behavior               |
| Đi lại   | 1.000.000       |   700.000 |   700.000 |   700.000 | on_track                      |

Ngân sách tháng 10 (50/30/20, dòng theo danh mục) có thêm dòng nhóm `savings` 5.000.000 — không
có advice. Mọi giao dịch Ăn uống ≤ 200.000 nên không giao dịch nào chiếm ≥ 60% phần vượt.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Budget
from app.schemas.budget import BudgetAllocationInput, BudgetCreate
from app.services import budget_service, category_service
from tests.review_dataset import Item

AUGUST = date(2026, 8, 1)
SEPTEMBER = date(2026, 9, 1)
OCTOBER = date(2026, 10, 1)
NOVEMBER = date(2026, 11, 1)
TODAY = "2026-11-02"


def _items(month: date, slug: str, count: int, amount: int, note: str, st: str) -> list[Item]:
    return [Item(month.replace(day=1 + i % 28), slug, amount, note, st) for i in range(count)]


LAPTOP = Item(date(2026, 10, 12), "shopping", 6_500_000, "Laptop", "irregular")

ITEMS: tuple[Item, ...] = (
    # Ăn uống 4.400.000 / 4.600.000 / 4.500.000
    *_items(AUGUST, "food", 22, 200_000, "Đi chợ", "essential"),
    *_items(SEPTEMBER, "food", 23, 200_000, "Đi chợ", "essential"),
    *_items(OCTOBER, "food", 30, 150_000, "Đi chợ", "essential"),
    # Mua sắm 1.500.000 / 1.500.000 / 8.000.000 (Laptop bất thường)
    Item(date(2026, 8, 20), "shopping", 1_500_000, "Áo khoác", "non_essential"),
    Item(date(2026, 9, 20), "shopping", 1_500_000, "Giày", "non_essential"),
    LAPTOP,
    *_items(OCTOBER, "shopping", 3, 500_000, "Quần áo", "non_essential"),
    # Giải trí 800.000 / 1.600.000 / 1.400.000
    *_items(AUGUST, "entertainment", 4, 200_000, "Xem phim", "non_essential"),
    *_items(SEPTEMBER, "entertainment", 8, 200_000, "Xem phim", "non_essential"),
    *_items(OCTOBER, "entertainment", 7, 200_000, "Xem phim", "non_essential"),
    # Đi lại 700.000 mỗi tháng
    *(
        i
        for m in (AUGUST, SEPTEMBER, OCTOBER)
        for i in _items(m, "transport", 7, 100_000, "Xăng", "essential")
    ),
    Item(date(2026, 10, 5), "salary", 25_000_000, "Lương tháng 10", None),
)

# (slug, nhóm, planned) — thứ tự dòng = thứ tự advice trả về.
ALLOCATIONS: tuple[tuple[str, str, int], ...] = (
    ("food", "essential", 4_000_000),
    ("shopping", "wants", 2_000_000),
    ("entertainment", "wants", 1_000_000),
    ("transport", "essential", 1_000_000),
)
SAVINGS_PLANNED = 5_000_000


def allocation_inputs(db: Session) -> list[BudgetAllocationInput]:
    return [
        BudgetAllocationInput(
            group=group,
            category_id=category_service.get_category_by_slug(db, slug).id,
            planned_amount=planned,
        )
        for slug, group, planned in ALLOCATIONS
    ] + [BudgetAllocationInput(group="savings", jar_name="savings", planned_amount=SAVINGS_PLANNED)]


def create_budget(
    db: Session,
    month: date = OCTOBER,
    *,
    status: str = "active",
    expected_income: int = 25_000_000,
    allocations: list[BudgetAllocationInput] | None = None,
) -> Budget:
    return budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=month,
            strategy="fifty_thirty_twenty",
            expected_income=expected_income,
            status=status,
            allocations=allocations or allocation_inputs(db),
            confirm_over_income=True,
        ),
    )
