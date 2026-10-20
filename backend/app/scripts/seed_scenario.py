"""Kịch bản Budget vs Actual cố định cho tháng 10/2026 (Phase 5) — dùng cho demo UI và test.

    python -m app.scripts.seed_scenario [--reset]

Tạo ngân sách **active** tháng 10/2026 (thu nhập dự kiến 25.000.000, 5 dòng theo danh mục) và
các giao dịch cố định trong 01–20/10/2026:

| Danh mục | Planned   | Actual    | Ghi chú                                   |
|----------|-----------|-----------|-------------------------------------------|
| Nhà ở    | 5.000.000 | 5.000.000 | đúng kế hoạch                             |
| Ăn uống  | 4.000.000 | 4.500.000 | vượt 500.000, không giao dịch nào nổi trội |
| Đi lại   | 1.000.000 |   700.000 | còn 300.000                               |
| Mua sắm  | 2.000.000 | 3.200.000 | vượt 1.200.000, tai nghe 900.000 (75%)    |
| Giải trí | 1.000.000 |   600.000 | còn 400.000                               |
| Thu nhập | 25.000.000 | 25.000.000 | lương                                    |

`--reset` xoá ngân sách và **mọi** giao dịch của tháng 10/2026 trước khi tạo.
"""

import argparse
import sys
from datetime import date

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.models import Budget
from app.repositories import budget_repository
from app.schemas.budget import BudgetAllocationInput, BudgetCreate
from app.schemas.transaction import TransactionCreate
from app.scripts.seed_demo import DemoTransaction
from app.services import budget_service, category_service, transaction_service
from app.services.money import month_range

SCENARIO_MONTH = date(2026, 10, 1)
EXPECTED_INCOME = 25_000_000
STRATEGY = "fifty_thirty_twenty"

# (slug danh mục, nhóm, planned)
ALLOCATIONS: tuple[tuple[str, str, int], ...] = (
    ("housing", "essential", 5_000_000),
    ("food", "essential", 4_000_000),
    ("transport", "essential", 1_000_000),
    ("shopping", "wants", 2_000_000),
    ("entertainment", "wants", 1_000_000),
)


def _d(day: int) -> date:
    return SCENARIO_MONTH.replace(day=day)


def _food() -> list[DemoTransaction]:
    # Nhiều khoản nhỏ (≤ 250.000) → vượt 500.000 nhưng không có top contributor.
    items = [DemoTransaction(_d(day), "food", 55_000, "Cơm trưa") for day in range(1, 21)]
    items += [
        DemoTransaction(_d(day), "food", 40_000, "Cà phê", "non_essential")
        for day in range(2, 21, 2)
    ]
    items += [DemoTransaction(_d(day), "food", 250_000, "Đi siêu thị") for day in (3, 8, 13, 18)]
    items += [
        DemoTransaction(_d(day), "food", 250_000, "Ăn tối nhà hàng", "non_essential")
        for day in (4, 6, 9, 11, 12, 15, 16, 19)
    ]
    return items


TRANSACTIONS: tuple[DemoTransaction, ...] = (
    DemoTransaction(_d(1), "housing", 5_000_000, "Tiền nhà tháng 10/2026"),
    DemoTransaction(_d(5), "salary", 25_000_000, "Lương tháng 10/2026"),
    *_food(),
    *(DemoTransaction(_d(day), "transport", 100_000, "Đổ xăng") for day in (4, 11, 18, 20)),
    *(DemoTransaction(_d(day), "transport", 100_000, "Grab đi làm") for day in (7, 14, 20)),
    DemoTransaction(_d(3), "shopping", 650_000, "Áo khoác"),
    DemoTransaction(_d(8), "shopping", 800_000, "Giày thể thao"),
    DemoTransaction(_d(12), "shopping", 900_000, "Tai nghe bluetooth"),
    DemoTransaction(_d(15), "shopping", 450_000, "Shopee đồ gia dụng"),
    DemoTransaction(_d(19), "shopping", 400_000, "Sách"),
    DemoTransaction(_d(10), "entertainment", 170_000, "Xem phim"),
    DemoTransaction(_d(15), "entertainment", 260_000, "Netflix + Spotify"),
    DemoTransaction(_d(17), "entertainment", 170_000, "Xem phim"),
)


class ScenarioExistsError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            f"Tháng {SCENARIO_MONTH:%m/%Y} đã có ngân sách hoặc giao dịch — chạy lại với --reset",
            "scenario_month_not_empty",
        )


def seed(db: Session, *, reset: bool = False) -> Budget:
    """Ghi kịch bản vào DB qua các service (validate như khi user nhập)."""
    start, end = month_range(SCENARIO_MONTH)
    existing = budget_repository.get_by_month(db, SCENARIO_MONTH)
    if reset:
        if existing is not None:
            budget_repository.delete(db, existing)
        transaction_service.delete_transactions_in_range(db, start, end)
    else:
        _, count = transaction_service.list_transactions(
            db,
            transaction_service.TransactionFilters(date_from=start, date_to=end),
            page=1,
            page_size=1,
        )
        if existing is not None or count:
            raise ScenarioExistsError

    slugs = {slug for slug, _, _ in ALLOCATIONS} | {t.category_slug for t in TRANSACTIONS}
    categories = {slug: category_service.get_category_by_slug(db, slug) for slug in slugs}
    for t in TRANSACTIONS:
        category = categories[t.category_slug]
        transaction_service.create_transaction(
            db,
            TransactionCreate(
                direction=category.kind,
                amount=t.amount,
                occurred_on=t.occurred_on,
                category_id=category.id,
                spending_type=t.spending_type,
                note=t.note,
            ),
        )
    return budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=SCENARIO_MONTH,
            strategy=STRATEGY,
            expected_income=EXPECTED_INCOME,
            status="active",
            allocations=[
                BudgetAllocationInput(
                    group=group, category_id=categories[slug].id, planned_amount=planned
                )
                for slug, group, planned in ALLOCATIONS
            ],
        ),
    )


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Tạo kịch bản Budget vs Actual tháng 10/2026.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Xoá ngân sách và MỌI giao dịch tháng 10/2026 trước khi tạo",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        try:
            budget = seed(db, reset=args.reset)
        except DomainError as exc:
            print(f"Lỗi: {exc.detail}", file=sys.stderr)
            return 1
    print(
        f"Đã tạo ngân sách tháng {SCENARIO_MONTH:%m/%Y} (id {budget.id}) và "
        f"{len(TRANSACTIONS)} giao dịch. Mở /budget?month={SCENARIO_MONTH:%Y-%m}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
