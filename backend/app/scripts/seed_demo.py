"""Sinh dữ liệu demo có quy luật cho DB dev (dùng cho Phase 5–9).

    python -m app.scripts.seed_demo --months 3 [--seed 42] [--reset] [--end 2026-10-08]

Kỳ sinh: `--months` tháng trọn vẹn trước tháng của `--end` + tháng hiện tại tới `--end`.
Quy luật: tiền nhà ngày 1, lương ngày 5, điện/nước/internet ~ngày 10–12, ăn uống gần như mỗi
ngày, đi lại, mua sắm/giải trí rải rác, đôi khi có khoản bất thường (irregular).
"""

import argparse
import random
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.schemas.transaction import TransactionCreate
from app.services import category_service, transaction_service
from app.services.money import add_months, month_range, round_vnd

INCOME_SLUGS = {"salary", "freelance", "bonus", "other_income"}


@dataclass(frozen=True)
class DemoTransaction:
    occurred_on: date
    category_slug: str
    amount: int
    note: str
    spending_type: str | None = None


def _amount(rng: random.Random, low: int, high: int, step: int = 1000) -> int:
    return round_vnd(rng.uniform(low, high), step)


def _days(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _monthly(d: date, rng: random.Random) -> Iterator[DemoTransaction]:
    month = f"{d.month}/{d.year}"
    if d.day == 1:
        yield DemoTransaction(d, "housing", 6_000_000, f"Tiền nhà tháng {month}")
    if d.day == 5:
        yield DemoTransaction(d, "salary", 25_000_000, f"Lương tháng {month}")
    if d.day == 10:
        yield DemoTransaction(d, "utilities", _amount(rng, 550_000, 1_100_000), "Tiền điện")
        yield DemoTransaction(d, "utilities", _amount(rng, 90_000, 180_000), "Tiền nước")
    if d.day == 12:
        yield DemoTransaction(d, "utilities", 280_000, "Internet + 4G")
    if d.day == 15:
        yield DemoTransaction(d, "entertainment", 260_000, "Netflix + Spotify")
    if d.day == 18 and rng.random() < 0.5:
        yield rng.choice(
            [
                DemoTransaction(
                    d, "transport", _amount(rng, 800_000, 2_000_000), "Sửa xe máy", "irregular"
                ),
                DemoTransaction(d, "electronics", 2_500_000, "Sửa laptop", "irregular"),
                DemoTransaction(
                    d, "health", _amount(rng, 600_000, 1_500_000), "Khám răng", "irregular"
                ),
            ]
        )
    if d.day == 20 and rng.random() < 0.4:
        amount = _amount(rng, 2_000_000, 5_000_000, 100_000)
        yield DemoTransaction(d, "freelance", amount, "Dự án freelance")
    if d.day == 22 and rng.random() < 0.3:
        amount = _amount(rng, 500_000, 1_000_000, 100_000)
        yield DemoTransaction(d, "gifts", amount, "Mừng cưới bạn")
    if d.day == 25 and rng.random() < 0.4:
        yield DemoTransaction(d, "health", _amount(rng, 150_000, 500_000), "Mua thuốc")


def _daily(d: date, rng: random.Random) -> Iterator[DemoTransaction]:
    weekday = d.weekday() < 5
    if weekday and rng.random() < 0.7:
        note = rng.choice(["Cơm trưa", "Bún bò", "Phở", "Bánh mì", "Cơm tấm"])
        yield DemoTransaction(d, "food", _amount(rng, 35_000, 70_000), note)
    if rng.random() < 0.3:
        yield DemoTransaction(d, "food", _amount(rng, 25_000, 60_000), "Cà phê", "non_essential")
    if weekday and rng.random() < 0.15:
        yield DemoTransaction(d, "transport", _amount(rng, 25_000, 70_000), "Grab đi làm")
    if d.weekday() == 5:
        yield DemoTransaction(d, "food", _amount(rng, 300_000, 700_000), "Đi siêu thị")
    if d.weekday() == 6:
        yield DemoTransaction(d, "transport", _amount(rng, 80_000, 120_000), "Đổ xăng")
    if not weekday and rng.random() < 0.35:
        note = rng.choice(["Ăn tối nhà hàng", "Lẩu với bạn", "Nướng cuối tuần"])
        yield DemoTransaction(d, "food", _amount(rng, 200_000, 500_000), note, "non_essential")
    if rng.random() < 0.06:
        note = rng.choice(["Mua áo", "Shopee", "Giày thể thao", "Đồ gia dụng"])
        yield DemoTransaction(d, "shopping", _amount(rng, 200_000, 1_200_000), note)
    if not weekday and rng.random() < 0.12:
        yield DemoTransaction(d, "entertainment", _amount(rng, 150_000, 250_000), "Xem phim")


def demo_period(end: date, months: int) -> tuple[date, date]:
    return month_range(add_months(end, -months))[0], end


def generate(start: date, end: date, seed: int = 42) -> list[DemoTransaction]:
    """Thuần (không chạm DB) → test được; cùng seed cho cùng kết quả."""
    rng = random.Random(seed)
    result: list[DemoTransaction] = []
    for d in _days(start, end):
        result.extend(_monthly(d, rng))
        result.extend(_daily(d, rng))
    return result


def main(argv: list[str] | None = None) -> int:
    # Console Windows (cp1252) không in được tiếng Việt.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Sinh giao dịch demo cho DB dev.")
    parser.add_argument("--months", type=int, default=3, help="Số tháng trọn vẹn (mặc định 3)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (mặc định 42)")
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=date.today(),
        help="Ngày cuối (YYYY-MM-DD), mặc định hôm nay",
    )
    parser.add_argument(
        "--reset", action="store_true", help="Xoá MỌI giao dịch trong kỳ sinh trước khi seed"
    )
    args = parser.parse_args(argv)
    if args.months < 1:
        parser.error("--months phải >= 1")

    start, end = demo_period(args.end, args.months)
    demo = generate(start, end, args.seed)

    with SessionLocal() as db:
        try:
            if args.reset:
                deleted = transaction_service.delete_transactions_in_range(db, start, end)
                print(f"Đã xoá {deleted} giao dịch từ {start} đến {end}.")
            categories = {
                slug: category_service.get_category_by_slug(db, slug)
                for slug in {t.category_slug for t in demo}
            }
            for t in demo:
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
        except DomainError as exc:
            print(f"Lỗi: {exc.detail}", file=sys.stderr)
            return 1

    income = sum(t.amount for t in demo if t.category_slug in INCOME_SLUGS)
    expense = sum(t.amount for t in demo) - income
    print(
        f"Đã tạo {len(demo)} giao dịch demo từ {start} đến {end} "
        f"(thu {income:,}đ, chi {expense:,}đ)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
