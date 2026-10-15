"""Parse câu nhập giao dịch tự nhiên → danh sách draft (chưa lưu DB).

Luồng: kiểm tra cấu hình AI → lấy danh mục đang dùng → build prompt (kèm lịch tham chiếu và số tiền
trích bằng quy tắc) → structured output → hậu kiểm slug/kind (sai thì model sửa 1 lần) → cảnh báo
deterministic về ngày và số tiền. Không ghi DB: user xác nhận rồi mới gọi `POST /transactions`.
"""

import re
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai import openai_client
from app.ai.openai_client import OutputValidationError
from app.core.errors import DomainError
from app.core.text import strip_accents
from app.models import Category
from app.schemas.ai import (
    DEFAULT_TIMEZONE,
    TransactionDraft,
    TransactionParseOutput,
    TransactionParseResponse,
)
from app.services import category_service
from app.services.amount_text import extract_amounts
from app.services.money import add_months, month_range, week_range

PROMPT_FILE = Path(__file__).parent / "prompts" / "nl_transaction_parse.v2.md"
TASK = "nl_transaction_parse"
MAX_PAST_DAYS = 366

# Số thứ đứng trước vì user hay viết "thứ 7", "t7" — tránh model nhầm thứ 5 / thứ 7.
WEEKDAYS = (
    "thứ 2 (Thứ Hai)",
    "thứ 3 (Thứ Ba)",
    "thứ 4 (Thứ Tư)",
    "thứ 5 (Thứ Năm)",
    "thứ 6 (Thứ Sáu)",
    "thứ 7 (Thứ Bảy)",
    "Chủ Nhật (CN)",
)
_MONEY_WORD_RE = re.compile(r"\b(nghin|ngan|trieu|cu|lit|ty|dong|k)\b")


@cache
def _prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def today_in(timezone: str = DEFAULT_TIMEZONE) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def _fmt(d: date) -> str:
    return f"{d.isoformat()} ({WEEKDAYS[d.weekday()]})"


def build_calendar(today: date) -> str:
    """Lịch tham chiếu để model không phải tự tính ngày tương đối (tuần bắt đầu Thứ Hai).

    Mỗi ngày một dòng `<thứ>: <ngày>` để model tra cứu "thứ 7 tuần trước" thay vì tự đếm.
    """
    this_monday, _ = week_range(today)
    last_monday = this_monday - timedelta(days=7)
    this_month = month_range(today)
    last_month = month_range(add_months(today, -1))

    def week(title: str, monday: date) -> list[str]:
        days = [monday + timedelta(days=i) for i in range(7)]
        return [f"  - {title}:"] + [
            f"    - {WEEKDAYS[d.weekday()]} {title.lower()}: {d.isoformat()}"
            + (" ← hôm nay" if d == today else "")
            + (" (tương lai)" if d > today else "")
            for d in days
        ]

    return "\n".join(
        [
            f"  - Hôm nay: {_fmt(today)}",
            f"  - Hôm qua: {_fmt(today - timedelta(days=1))}",
            f"  - Hôm kia: {_fmt(today - timedelta(days=2))}",
            *week("Tuần này", this_monday),
            *week("Tuần trước", last_monday),
            f"  - Tháng này: {this_month[0].isoformat()} → {this_month[1].isoformat()}",
            f"  - Tháng trước: {last_month[0].isoformat()} → {last_month[1].isoformat()}",
        ]
    )


def build_messages(
    text: str, today: date, categories: list[Category], timezone: str = DEFAULT_TIMEZONE
) -> list[openai_client.Message]:
    rows = "\n".join(
        f"| {c.slug} | {c.name} | {c.kind} | {c.default_spending_type or '—'} |" for c in categories
    )
    hints = extract_amounts(text)
    amount_hints = (
        ", ".join(str(a) for a in hints) if hints else "(không phát hiện được bằng quy tắc)"
    )
    system = (
        _prompt_template()
        .replace("{{today}}", today.isoformat())
        .replace("{{weekday}}", WEEKDAYS[today.weekday()])
        .replace("{{timezone}}", timezone)
        .replace("{{calendar}}", build_calendar(today))
        .replace("{{categories}}", rows)
        .replace("{{amount_hints}}", amount_hints)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _ensure_has_amount(text: str) -> None:
    normalized = strip_accents(text).lower()
    if not any(ch.isdigit() for ch in normalized) and not _MONEY_WORD_RE.search(normalized):
        raise DomainError(
            "Mình chưa thấy số tiền trong câu. Bạn thêm số tiền giúp nhé, ví dụ: “ăn phở 55k”.",
            "amount_missing",
        )


def _validator(categories_by_slug: dict[str, Category]):
    def validate(output: TransactionParseOutput) -> None:
        problems = []
        for i, tx in enumerate(output.transactions, start=1):
            category = categories_by_slug.get(tx.category_slug)
            if category is None:
                problems.append(f"giao dịch {i}: category_slug '{tx.category_slug}' không có")
            elif category.kind != tx.direction:
                problems.append(
                    f"giao dịch {i}: category '{tx.category_slug}' có kind {category.kind}, "
                    f"không khớp direction {tx.direction}"
                )
        if problems:
            allowed = {
                kind: ", ".join(s for s, c in categories_by_slug.items() if c.kind == kind)
                for kind in ("expense", "income")
            }
            raise OutputValidationError(
                "; ".join(problems)
                + f". Slug hợp lệ — expense: {allowed['expense']}; income: {allowed['income']}"
            )

    return validate


def _format_vnd(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + " ₫"


def _deterministic_warnings(text: str, drafts: list[TransactionDraft], today: date) -> list[str]:
    warnings: list[str] = []
    hints = extract_amounts(text)
    if hints:
        unexpected = [d.amount for d in drafts if d.amount not in hints]
        for amount in unexpected:
            warnings.append(
                f"Số tiền {_format_vnd(amount)} không thấy trong câu gốc — "
                "bạn kiểm tra lại giúp nhé."
            )
        if len(drafts) < len(hints):
            warnings.append(
                f"Câu có {len(hints)} khoản tiền nhưng mới tách được {len(drafts)} giao dịch — "
                "bạn xem có thiếu khoản nào không nhé."
            )
    for d in drafts:
        if d.occurred_on > today:
            warnings.append(
                f"“{d.note}” có ngày {d.occurred_on.isoformat()} ở tương lai — "
                "bạn kiểm tra lại ngày giúp nhé."
            )
        elif (today - d.occurred_on).days > MAX_PAST_DAYS:
            warnings.append(
                f"“{d.note}” có ngày {d.occurred_on.isoformat()} cách đây hơn một năm — "
                "bạn kiểm tra lại ngày giúp nhé."
            )
    return warnings


def parse_transactions(
    db: Session, text: str, *, today: date | None = None, timezone: str = DEFAULT_TIMEZONE
) -> TransactionParseResponse:
    openai_client.ensure_configured()
    text = text.strip()
    _ensure_has_amount(text)
    today = today or today_in(timezone)

    categories = category_service.list_categories(db)
    categories_by_slug = {c.slug: c for c in categories}

    output, model = openai_client.structured_completion(
        TransactionParseOutput,
        build_messages(text, today, categories, timezone),
        task=TASK,
        model=openai_client.model_fast(),
        validate=_validator(categories_by_slug),
    )

    drafts = [
        TransactionDraft(
            **tx.model_dump(),
            category_id=categories_by_slug[tx.category_slug].id,
        )
        for tx in output.transactions
    ]
    warnings = [w.strip() for w in output.warnings if w.strip()]
    warnings += _deterministic_warnings(text, drafts, today)
    return TransactionParseResponse(drafts=drafts, model=model, raw_input=text, warnings=warnings)
