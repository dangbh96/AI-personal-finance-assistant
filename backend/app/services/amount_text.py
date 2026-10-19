"""Trích số tiền gõ tắt tiếng Việt từ câu tự nhiên (deterministic, không dùng AI).

Dùng để gợi ý cho prompt và hậu kiểm `amount` do AI trả về (ADR-005). Quy ước theo glossary:

    "55k" | "55 nghìn" | "55.000" | "55000"      → 55_000
    "1tr5" | "1.5tr" | "1,5 triệu" | "1 triệu rưỡi" → 1_500_000
    "1tr250"                                       → 1_250_000
    "25 triệu" | "25m"                             → 25_000_000
    "1 củ" → 1_000_000 · "2 lít" → 200_000 · "1 tỷ" → 1_000_000_000

Số không kèm đơn vị chỉ được tính khi >= 1.000 và không phải năm / ngày tháng
(tránh "thứ 7", "2 ly", "năm 2026", "07/10/2026").
"""

import re
import unicodedata

from app.core.text import strip_accents

UNITS: dict[str, int] = {
    "k": 1_000,
    "nghin": 1_000,
    "ngan": 1_000,
    "lit": 100_000,
    "trieu": 1_000_000,
    "tr": 1_000_000,
    "cu": 1_000_000,
    "m": 1_000_000,
    "ty": 1_000_000_000,
}

MIN_BARE_AMOUNT = 1_000

_UNIT_RE = "|".join(sorted(UNITS, key=len, reverse=True))
_AMOUNT_RE = re.compile(
    rf"(?<![\w.,/:-])(?P<number>\d+(?:[.,]\d+)*)(?![/:-]\d)\s*"
    rf"(?:(?P<unit>{_UNIT_RE})(?:(?P<tail>\d+)\b|\s+(?P<half>ruoi)\b|\b))?"
)
_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_YEAR_PREFIX_RE = re.compile(r"\bnam\s*$")


def _scaled(int_part: str, fraction: str, multiplier: int) -> int:
    """`int_part.fraction × multiplier`, làm tròn nửa lên, chỉ dùng số nguyên (ADR-007)."""
    value = int(int_part) * multiplier
    if fraction:
        denominator = 10 ** len(fraction)
        value += (int(fraction) * multiplier * 2 + denominator) // (2 * denominator)
    return value


def _to_amount(match: re.Match[str]) -> int | None:
    number, unit = match["number"], match["unit"]
    if unit is None:
        if _YEAR_PREFIX_RE.search(match.string, 0, match.start()):
            return None
        if _THOUSANDS_RE.match(number):
            value = int(re.sub(r"[.,]", "", number))
        elif number.isdigit():
            value = int(number)
        else:
            return None
        return value if value >= MIN_BARE_AMOUNT else None

    multiplier = UNITS[unit]
    parts = re.split(r"[.,]", number)
    if len(parts) > 2:
        return None
    int_part, fraction = parts[0], parts[1] if len(parts) == 2 else ""
    if match["tail"]:
        if fraction:
            return None
        fraction = match["tail"]
    value = _scaled(int_part, fraction, multiplier)
    if match["half"]:
        value += multiplier // 2
    return value if value > 0 else None


_CURRENCY_SUFFIX_RE = re.compile(r"\s*(?:vnd|dong|d)\b")


def _matches(normalized: str) -> list[tuple[re.Match[str], int]]:
    return [(m, a) for m in _AMOUNT_RE.finditer(normalized) if (a := _to_amount(m)) is not None]


def extract_amounts(text: str) -> list[int]:
    """Các số tiền (đồng) xuất hiện trong câu, theo thứ tự xuất hiện."""
    return [amount for _, amount in _matches(strip_accents(text).lower())]


def amount_spans(normalized: str) -> list[tuple[int, int]]:
    """Vị trí `[start, end)` của các số tiền (kèm "đ"/"vnđ" ngay sau) trong câu **đã** bỏ dấu +
    lowercase."""
    spans = []
    for match, _ in _matches(normalized):
        end = match.end()
        if suffix := _CURRENCY_SUFFIX_RE.match(normalized, end):
            end = suffix.end()
        spans.append((match.start(), end))
    return spans


def remove_amounts(text: str) -> str:
    """Bỏ các số tiền khỏi câu gốc (giữ dấu): "Mua giày Nike 2tr" → "Mua giày Nike"."""
    original = unicodedata.normalize("NFC", text)
    normalized = strip_accents(original).lower()
    if len(normalized) != len(original):  # hiếm: ký tự không map 1-1 sau khi bỏ dấu
        return " ".join(original.split())
    for start, end in reversed(amount_spans(normalized)):
        original = f"{original[:start]} {original[end:]}"
    return " ".join(original.split())
