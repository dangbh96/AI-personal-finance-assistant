"""Parse câu nhập giao dịch tự nhiên → danh sách draft (chưa lưu DB).

Luồng: chặn câu không có số tiền → lấy danh mục đang dùng + preference đã học →
- câu đơn giản (1 khoản tiền, không nêu ngày) khớp exact một preference → draft deterministic,
  **không gọi OpenAI** (Phase 3);
- còn lại: build prompt (lịch tham chiếu, số tiền trích bằng quy tắc, top-5 preference liên quan)
  → structured output → hậu kiểm slug/kind (sai thì model sửa 1 lần) → khoản nào exact-match
  preference thì phân loại theo preference.
Cuối cùng thêm cảnh báo deterministic về ngày và số tiền. Không ghi DB: user xác nhận rồi mới gọi
`POST /transactions`.
"""

import re
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.ai import classifier, openai_client
from app.ai.openai_client import OutputValidationError
from app.core.errors import DomainError
from app.core.text import strip_accents
from app.models import Category, ClassificationPreference
from app.schemas.ai import (
    DEFAULT_TIMEZONE,
    TransactionDraft,
    TransactionParseOutput,
    TransactionParseResponse,
)
from app.services import category_service, classification_preference_service
from app.services.amount_text import extract_amounts, remove_amounts
from app.services.classification_text import has_digits_besides_amounts, tokenize
from app.services.money import add_months, month_range, week_range

PROMPT_FILE = Path(__file__).parent / "prompts" / "nl_transaction_parse.v3.md"
TASK = "nl_transaction_parse"
PREFERENCE_MODEL = "classification_preference"
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

# Câu có các từ này cần model hiểu (ngày tương đối, chiều tiền) → không dùng shortcut.
_DATE_TOKENS = frozenset(
    {"qua", "kia", "mai", "thu", "tuan", "thang", "ngay", "nam", "truoc", "sau", "cn", "chu"}
)
_WEEKDAY_TOKEN_RE = re.compile(r"^t[2-8]$")
_INCOME_TOKENS = frozenset({"nhan", "hoan", "ban", "luong", "thuong", "duoc", "lai"})
_EXPENSE_TOKENS = frozenset({"mua", "tra", "chi", "dong", "nop", "het", "mat"})
_LEADING_TIME_RE = re.compile(r"^(?:hôm nay|(?:sáng|trưa|chiều|tối)(?: nay)?|nay)\s+", re.I)


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
    text: str,
    today: date,
    categories: list[Category],
    timezone: str = DEFAULT_TIMEZONE,
    preferences: list[ClassificationPreference] | None = None,
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
        .replace("{{preferences}}", classifier.format_few_shot(preferences or []))
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


def _shortcut_note(text: str) -> str:
    note = _LEADING_TIME_RE.sub("", remove_amounts(text)).strip(" ,.;:-–")
    return note[:1].upper() + note[1:]


def preference_shortcut(
    text: str, today: date, preferences: list[ClassificationPreference]
) -> TransactionDraft | None:
    """Draft deterministic (không gọi AI) khi câu chỉ có 1 khoản tiền, không nêu ngày / chiều tiền
    mơ hồ, và khớp exact một preference: "Mua giày Nike 2tr" + preference "giay"."""
    amounts = extract_amounts(text)
    if len(amounts) != 1 or has_digits_besides_amounts(text):
        return None
    tokens = set(tokenize(text))
    if tokens & _DATE_TOKENS or any(_WEEKDAY_TOKEN_RE.match(t) for t in tokens):
        return None
    preference = classifier.match_preference(text, preferences)
    if preference is None:
        return None
    direction = preference.category.kind
    conflicting = _INCOME_TOKENS if direction == "expense" else _EXPENSE_TOKENS
    if tokens & conflicting:
        return None

    suggestion = classifier.suggestion_from_preference(preference)
    return TransactionDraft(
        direction=direction,
        amount=amounts[0],
        occurred_on=today,
        note=_shortcut_note(text) or preference.category.name,
        category_slug=suggestion.category_slug,
        category_id=preference.category_id,
        spending_type=(suggestion.spending_type or preference.category.default_spending_type)
        if direction == "expense"
        else None,
        confidence=suggestion.confidence,
        reason=suggestion.reason,
        matched_preference_id=preference.id,
    )


def parse_transactions(
    db: Session, text: str, *, today: date | None = None, timezone: str = DEFAULT_TIMEZONE
) -> TransactionParseResponse:
    text = text.strip()
    _ensure_has_amount(text)
    today = today or today_in(timezone)
    preferences = classification_preference_service.active_preferences(db)

    if (shortcut := preference_shortcut(text, today, preferences)) is not None:
        return TransactionParseResponse(
            drafts=[shortcut],
            model=PREFERENCE_MODEL,
            raw_input=text,
            warnings=_deterministic_warnings(text, [shortcut], today),
        )

    openai_client.ensure_configured()
    categories = category_service.list_categories(db)
    categories_by_slug = {c.slug: c for c in categories}
    few_shot = classification_preference_service.related(preferences, set(tokenize(text)))

    output, model = openai_client.structured_completion(
        TransactionParseOutput,
        build_messages(text, today, categories, timezone, few_shot),
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
    drafts = classifier.apply_preferences(drafts, preferences, text)
    warnings = [w.strip() for w in output.warnings if w.strip()]
    warnings += _deterministic_warnings(text, drafts, today)
    return TransactionParseResponse(drafts=drafts, model=model, raw_input=text, warnings=warnings)
