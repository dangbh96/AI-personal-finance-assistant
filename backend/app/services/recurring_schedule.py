"""Lịch khoản định kỳ — hàm thuần, deterministic (Phase 12, ADR-005).

- `monthly`: ngày `day_of_month` mỗi tháng; tháng không có ngày đó → ngày cuối tháng (31 → 28/29/02,
  30/04…), tháng sau lại về đúng ngày gốc.
- `weekly`: thứ `day_of_week` (ISO, Thứ Hai = 1).
- `yearly`: ngày `day_of_month` của tháng `month` mỗi năm (29/02 → 28/02 năm không nhuận).
- "Kỳ kế tiếp" luôn **sau** ngày đang xét (`next_occurrence`); kỳ đầu của khoản mới = kỳ đầu tiên
  sau hôm nay (plan: ngày tính ra <= hôm nay → nhảy tới kỳ kế tiếp).
- `calendar_icon`: icon lịch theo chiều / danh mục / tên (heuristic từ khoá, không AI).
"""

import calendar
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.text import strip_accents

UPCOMING_DAYS = 14


@dataclass(frozen=True)
class ScheduleRule:
    frequency: str
    day_of_month: int | None = None
    day_of_week: int | None = None
    month: int | None = None  # chỉ yearly

    def __post_init__(self) -> None:
        if self.frequency == "weekly":
            if self.day_of_week is None or not 1 <= self.day_of_week <= 7:
                raise ValueError("weekly cần day_of_week 1–7")
        elif self.frequency in ("monthly", "yearly"):
            if self.day_of_month is None or not 1 <= self.day_of_month <= 31:
                raise ValueError(f"{self.frequency} cần day_of_month 1–31")
            if self.frequency == "yearly" and (self.month is None or not 1 <= self.month <= 12):
                raise ValueError("yearly cần month 1–12")
        else:
            raise ValueError(f"frequency không hợp lệ: {self.frequency}")


def day_in_month(year: int, month: int, day: int) -> date:
    """Ngày `day` của tháng, kẹp về ngày cuối nếu tháng ngắn hơn."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_occurrence(rule: ScheduleRule, current: date) -> date:
    """Kỳ đầu tiên **sau** `current` (không tính chính `current`)."""
    if rule.frequency == "weekly":
        assert rule.day_of_week is not None
        delta = (rule.day_of_week - current.isoweekday()) % 7 or 7
        return current + timedelta(days=delta)
    assert rule.day_of_month is not None
    if rule.frequency == "monthly":
        candidate = day_in_month(current.year, current.month, rule.day_of_month)
        if candidate > current:
            return candidate
        index = current.year * 12 + current.month  # tháng sau (0-based + 1)
        year, month0 = divmod(index, 12)
        return day_in_month(year, month0 + 1, rule.day_of_month)
    assert rule.month is not None
    candidate = day_in_month(current.year, rule.month, rule.day_of_month)
    if candidate > current:
        return candidate
    return day_in_month(current.year + 1, rule.month, rule.day_of_month)


def first_on_or_after(rule: ScheduleRule, day: date) -> date:
    return next_occurrence(rule, day - timedelta(days=1))


def is_occurrence(rule: ScheduleRule, day: date) -> bool:
    return first_on_or_after(rule, day) == day


def occurrences(rule: ScheduleRule, first_due: date, start: date, end: date) -> Iterator[date]:
    """Các kỳ từ `first_due` trở đi nằm trong `[start, end]`."""
    day = first_due
    while day <= end:
        if day >= start:
            yield day
        day = next_occurrence(rule, day)


def days_until(due: date, today: date) -> int:
    return (due - today).days


def due_status(due: date, today: date) -> str:
    days = days_until(due, today)
    if days < 0:
        return "overdue"
    if days == 0:
        return "due_today"
    return "upcoming" if days <= UPCOMING_DAYS else "later"


# ---------- icon lịch ----------

ICON_INCOME = "💰"
ICON_RENT = "🏠"
ICON_CREDIT_CARD = "💳"
ICON_UTILITIES = "📱"
ICON_GOAL = "🎯"
ICON_DEFAULT = "🔁"

_CREDIT_CARD_WORDS = ("the tin dung", "credit card", "credit", "visa", "mastercard", "sao ke")
_RENT_WORDS = ("thue nha", "tien nha", "nha tro", "phong tro", "tien phong", "rent")
_UTILITY_WORDS = (
    "internet",
    "wifi",
    "mang",
    "dien thoai",
    "4g",
    "5g",
    "cuoc",
    "tien dien",
    "tien nuoc",
    "truyen hinh",
    "netflix",
    "spotify",
    "youtube",
)


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    padded = f" {text} "
    return any(f" {w} " in padded for w in words)


def calendar_icon(direction: str, category_slug: str | None, name: str | None) -> str:
    """💰 thu nhập · 💳 thẻ tín dụng (theo tên) · 🏠 nhà ở · 📱 internet / điện thoại / tiện ích ·
    còn lại 🔁. Thứ tự ưu tiên như liệt kê."""
    if direction == "income":
        return ICON_INCOME
    text = " ".join(strip_accents(name or "").lower().replace("-", " ").split())
    if _has_word(text, _CREDIT_CARD_WORDS):
        return ICON_CREDIT_CARD
    if category_slug == "housing" or _has_word(text, _RENT_WORDS):
        return ICON_RENT
    if category_slug == "utilities" or _has_word(text, _UTILITY_WORDS):
        return ICON_UTILITIES
    return ICON_DEFAULT
