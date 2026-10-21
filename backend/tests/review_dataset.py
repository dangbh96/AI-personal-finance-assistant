"""Dữ liệu cố định cho test Weekly review (phase-06 § 6).

| Tuần        | Thu | Chi       | Ăn uống   | Thiết yếu | Không thiết yếu | Bất thường |
|-------------|-----|-----------|-----------|-----------|-----------------|------------|
| 05–11/10/26 | 0   | 1.900.000 | 1.000.000 | 1.550.000 |         350.000 |          0 |
| 12–18/10/26 | 0   | 2.242.000 | 1.180.000 | 1.420.000 |         672.000 |    150.000 |

Tuần 2: chi +18%, Ăn uống +18% (tăng nhiều nhất), 4 lần ăn tối (120k + 150k + 180k + 170k =
620.000), Mua sắm giảm 150.000.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models import Transaction
from app.schemas.transaction import TransactionCreate
from app.services import category_service, transaction_service
from app.services.review_metrics import TxRow

WEEK_1 = date(2026, 10, 5)
WEEK_2 = date(2026, 10, 12)

CATEGORY_NAMES = {
    "housing": "Nhà ở",
    "food": "Ăn uống",
    "transport": "Đi lại",
    "utilities": "Hoá đơn & tiện ích",
    "shopping": "Mua sắm",
    "entertainment": "Giải trí",
    "health": "Sức khoẻ",
    "electronics": "Điện tử",
    "other": "Khác",
    "salary": "Lương",
}


@dataclass(frozen=True)
class Item:
    day: date
    slug: str
    amount: int
    note: str
    spending_type: str | None = "essential"

    @property
    def direction(self) -> str:
        return "income" if self.slug == "salary" else "expense"


def _d(day: int) -> date:
    return date(2026, 10, day)


WEEK_1_ITEMS: tuple[Item, ...] = (
    Item(_d(5), "food", 400_000, "Đi siêu thị"),
    *(Item(_d(day), "food", 80_000, "Cơm trưa") for day in range(6, 11)),
    Item(_d(9), "food", 200_000, "Ăn tối cùng đồng nghiệp", "non_essential"),
    Item(_d(7), "transport", 300_000, "Đổ xăng"),
    Item(_d(8), "utilities", 450_000, "Tiền điện"),
    Item(_d(10), "shopping", 150_000, "Ốp lưng điện thoại", "non_essential"),
)

DINNERS: tuple[Item, ...] = (
    Item(_d(12), "food", 120_000, "Ăn tối lẩu", "non_essential"),
    Item(_d(14), "food", 150_000, "Đặt đồ ăn tối", "non_essential"),
    Item(_d(16), "food", 180_000, "Ăn tối nhà hàng", "non_essential"),
    Item(_d(17), "food", 170_000, "Đặt đồ ăn tối", "non_essential"),
)

WEEK_2_ITEMS: tuple[Item, ...] = (
    *DINNERS,
    Item(_d(13), "food", 360_000, "Đi siêu thị"),
    Item(_d(13), "food", 100_000, "Cơm trưa"),
    Item(_d(15), "food", 100_000, "Cơm trưa"),
    Item(_d(14), "transport", 360_000, "Đổ xăng"),
    Item(_d(15), "utilities", 500_000, "Tiền internet + điện"),
    Item(_d(18), "entertainment", 52_000, "Spotify", "non_essential"),
    Item(_d(16), "health", 150_000, "Thuốc cảm", "irregular"),
)


def _category_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"category/{slug}")


def to_rows(items: tuple[Item, ...]) -> list[TxRow]:
    """TxRow giả (không cần DB) cho test hàm thuần."""
    return [
        TxRow(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"tx/{i.day}/{i.note}/{i.amount}/{n}"),
            occurred_on=i.day,
            direction=i.direction,
            amount=i.amount,
            note=i.note,
            category_id=_category_id(i.slug),
            category_slug=i.slug,
            category_name=CATEGORY_NAMES[i.slug],
            category_icon=None,
            spending_type=i.spending_type if i.direction == "expense" else None,
        )
        for n, i in enumerate(items)
    ]


def seed(db: Session, items: tuple[Item, ...] = WEEK_1_ITEMS + WEEK_2_ITEMS) -> list[Transaction]:
    """Ghi giao dịch vào DB test qua service (cùng validate như user nhập)."""
    created = []
    for i in items:
        category = category_service.get_category_by_slug(db, i.slug)
        created.append(
            transaction_service.create_transaction(
                db,
                TransactionCreate(
                    direction=i.direction,
                    amount=i.amount,
                    occurred_on=i.day,
                    category_id=category.id,
                    spending_type=i.spending_type if i.direction == "expense" else None,
                    note=i.note,
                ),
            )
        )
    return created
