"""Dữ liệu cố định cho test Financial Coach (phase-10 § 6).

| Danh mục | 07/2026   | 08/2026   | 09/2026   | Hạng biến động |
|----------|-----------|-----------|-----------|----------------|
| Ăn uống  | 4.000.000 | 4.100.000 | 4.200.000 | 3              |
| Mua sắm  | 1.500.000 | 1.000.000 | 3.800.000 | 1 (Nồi chiên 2.000.000 bất thường) |
| Giải trí |   900.000 | 1.300.000 | 1.100.000 | 2              |

Ngân sách 09/2026 (active): Ăn uống 4.000.000, Mua sắm 2.000.000 (vượt 1.800.000), Giải trí
1.000.000. Ngân sách 10/2026 (active, tháng đang chạy tới 05/10): Mua sắm 2.000.000, đã chi 500.000.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Budget
from app.schemas.budget import BudgetAllocationInput, BudgetCreate
from app.services import budget_service, category_service
from tests.review_dataset import Item, seed

JULY = date(2026, 7, 1)
AUGUST = date(2026, 8, 1)
SEPTEMBER = date(2026, 9, 1)
OCTOBER = date(2026, 10, 1)
TODAY = date(2026, 10, 5)


def _d(month: date, day: int) -> date:
    return month.replace(day=day)


ITEMS: tuple[Item, ...] = (
    # Ăn uống 4.000.000 / 4.100.000 / 4.200.000
    Item(_d(JULY, 3), "food", 2_000_000, "Đi chợ"),
    Item(_d(JULY, 18), "food", 2_000_000, "Đi chợ"),
    Item(_d(AUGUST, 3), "food", 2_000_000, "Đi chợ"),
    Item(_d(AUGUST, 18), "food", 2_100_000, "Đi chợ"),
    Item(_d(SEPTEMBER, 3), "food", 2_100_000, "Đi chợ"),
    Item(_d(SEPTEMBER, 18), "food", 2_100_000, "Đi chợ"),
    # Mua sắm 1.500.000 / 1.000.000 / 3.800.000
    Item(_d(JULY, 10), "shopping", 1_500_000, "Áo khoác", "non_essential"),
    Item(_d(AUGUST, 10), "shopping", 1_000_000, "Giày", "non_essential"),
    Item(_d(SEPTEMBER, 8), "shopping", 2_000_000, "Nồi chiên", "irregular"),
    Item(_d(SEPTEMBER, 12), "shopping", 1_200_000, "Quần áo", "non_essential"),
    Item(_d(SEPTEMBER, 25), "shopping", 600_000, "Phụ kiện", "non_essential"),
    # Giải trí 900.000 / 1.300.000 / 1.100.000
    Item(_d(JULY, 20), "entertainment", 900_000, "Xem phim", "non_essential"),
    Item(_d(AUGUST, 20), "entertainment", 1_300_000, "Concert", "non_essential"),
    Item(_d(SEPTEMBER, 20), "entertainment", 1_100_000, "Xem phim", "non_essential"),
    # Thu nhập
    Item(_d(JULY, 5), "salary", 25_000_000, "Lương tháng 7", None),
    Item(_d(AUGUST, 5), "salary", 25_000_000, "Lương tháng 8", None),
    Item(_d(SEPTEMBER, 5), "salary", 25_000_000, "Lương tháng 9", None),
    # Tháng 10 (đang chạy)
    Item(_d(OCTOBER, 2), "shopping", 500_000, "Áo thun", "non_essential"),
    Item(_d(OCTOBER, 3), "food", 600_000, "Đi chợ"),
)

# (slug, nhóm, planned)
ALLOCATIONS: tuple[tuple[str, str, int], ...] = (
    ("food", "essential", 4_000_000),
    ("shopping", "wants", 2_000_000),
    ("entertainment", "wants", 1_000_000),
)


def create_budget(db: Session, month: date) -> Budget:
    return budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=month,
            strategy="fifty_thirty_twenty",
            expected_income=25_000_000,
            status="active",
            allocations=[
                BudgetAllocationInput(
                    group=group,
                    category_id=category_service.get_category_by_slug(db, slug).id,
                    planned_amount=planned,
                )
                for slug, group, planned in ALLOCATIONS
            ],
            confirm_over_income=True,
        ),
    )


def seed_all(db: Session) -> dict[date, Budget]:
    seed(db, ITEMS)
    return {month: create_budget(db, month) for month in (SEPTEMBER, OCTOBER)}
