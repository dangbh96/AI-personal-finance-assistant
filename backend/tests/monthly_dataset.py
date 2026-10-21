"""Dữ liệu cố định cho test Monthly review (phase-07 § 6).

| Tháng   | Thu        | Chi        | Thiết yếu | Không thiết yếu | Bất thường |
|---------|------------|------------|-----------|-----------------|------------|
| 09/2026 | 25.000.000 | 18.400.000 | 9.200.000 |       6.100.000 |  3.100.000 |
| 10/2026 | 25.000.000 | 20.608.000 | 4.448.000 |       1.160.000 | 15.000.000 |

- Tháng 9: còn lại 6.600.000, tỉ lệ tiết kiệm 26,4%; tỉ trọng 50% / 33,2% / 16,8%.
- Tháng 10: chi +12% so với tháng 9, phần lớn do Laptop 15.000.000 (Điện tử, bất thường); còn lại
  4.392.000 (17,6%). Ăn uống 4.500.000 so với ngân sách 4.000.000 → vượt 500.000.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Budget
from app.schemas.budget import BudgetAllocationInput, BudgetCreate
from app.services import budget_service, category_service
from tests.review_dataset import Item

SEPTEMBER = date(2026, 9, 1)
OCTOBER = date(2026, 10, 1)
TODAY = date(2026, 11, 2)


def _sep(day: int) -> date:
    return date(2026, 9, day)


def _oct(day: int) -> date:
    return date(2026, 10, day)


SEP_ITEMS: tuple[Item, ...] = (
    Item(_sep(5), "salary", 25_000_000, "Lương tháng 9", None),
    # Thiết yếu 9.200.000
    Item(_sep(1), "housing", 5_000_000, "Tiền nhà"),
    *(Item(_sep(day), "food", 700_000, "Đi siêu thị") for day in (3, 10, 17, 24)),
    *(Item(_sep(day), "transport", 100_000, "Đổ xăng") for day in (2, 9, 16, 23)),
    Item(_sep(8), "utilities", 1_000_000, "Tiền điện"),
    # Không thiết yếu 6.100.000
    Item(_sep(6), "shopping", 1_500_000, "Áo khoác", "non_essential"),
    Item(_sep(20), "shopping", 2_000_000, "Giày thể thao", "non_essential"),
    *(
        Item(_sep(day), "food", 300_000, "Ăn tối nhà hàng", "non_essential")
        for day in (4, 11, 12, 18, 25, 26)
    ),
    *(
        Item(_sep(day), "entertainment", 200_000, "Xem phim", "non_essential")
        for day in (7, 14, 21, 28)
    ),
    # Bất thường 3.100.000
    Item(_sep(15), "health", 2_000_000, "Khám răng", "irregular"),
    Item(_sep(22), "other", 1_100_000, "Sửa xe máy", "irregular"),
)

LAPTOP = Item(_oct(10), "electronics", 15_000_000, "Laptop", "irregular")
OCT_DINNERS: tuple[Item, ...] = tuple(
    Item(_oct(day), "food", 300_000, "Ăn tối nhà hàng", "non_essential") for day in (9, 16, 23)
)

OCT_ITEMS: tuple[Item, ...] = (
    Item(_oct(5), "salary", 25_000_000, "Lương tháng 10", None),
    LAPTOP,
    # Ăn uống 4.500.000
    *(Item(_oct(day), "food", 750_000, "Đi siêu thị") for day in (3, 10, 17, 24)),
    *(Item(_oct(day), "food", 60_000, "Cơm trưa") for day in (5, 6, 7, 8, 9, 12, 13, 14, 15, 16)),
    *OCT_DINNERS,
    *(Item(_oct(day), "transport", 100_000, "Đổ xăng") for day in (2, 9, 16, 23)),
    Item(_oct(8), "utilities", 448_000, "Tiền điện"),
    Item(_oct(15), "entertainment", 260_000, "Netflix + Spotify", "non_essential"),
)

# (slug, nhóm, planned) — ngân sách tháng 10 theo danh mục.
OCT_ALLOCATIONS: tuple[tuple[str, str, int], ...] = (
    ("food", "essential", 4_000_000),
    ("transport", "essential", 1_000_000),
    ("utilities", "essential", 500_000),
    ("entertainment", "wants", 500_000),
)


def create_october_budget(db: Session, status: str = "active") -> Budget:
    return budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=OCTOBER,
            strategy="fifty_thirty_twenty",
            expected_income=25_000_000,
            status=status,
            allocations=[
                BudgetAllocationInput(
                    group=group,
                    category_id=category_service.get_category_by_slug(db, slug).id,
                    planned_amount=planned,
                )
                for slug, group, planned in OCT_ALLOCATIONS
            ],
        ),
    )
