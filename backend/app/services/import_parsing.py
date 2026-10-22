"""Chuẩn hoá sao kê ngân hàng (Phase 14) — hàm thuần, deterministic, có unit test (ADR-005).

Bảng thô (`import_reader`) → dòng tiêu đề → đoán mapping cột → chuẩn hoá từng dòng:

- Ngày `dd/mm/yyyy` (mặc định Việt Nam), `mm/dd/yyyy`, `yyyy-mm-dd`, số serial Excel; bỏ giờ.
- Số tiền `1.500.000`, `1,500,000.00`, `(1.500.000)`, `-1.500.000`, `1.500.000 VND` → số nguyên
  đồng.
- `direction = expense` nếu ghi nợ > 0 hoặc số tiền < 0; `income` nếu ghi có > 0 hoặc số tiền > 0;
  `amount` luôn là giá trị tuyệt đối (ADR-007).
- `dedup_hash = sha256(ngày|số tiền|chiều|nội dung đã chuẩn hoá)`; dòng sau trong file có cùng
  hash → `duplicate`; hash đã có trong DB → `duplicate`.
"""

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.core.text import strip_accents
from app.schemas.common import MAX_AMOUNT
from app.schemas.imports import ColumnMapping, DateFormat, DecimalStyle
from app.services.money import round_vnd

HEADER_SCAN_ROWS = 30
MAX_NOTE_LENGTH = 500
MAX_PROMPT_NOTE_LENGTH = 160
DEFAULT_DATE_FORMAT: DateFormat = "dd/mm/yyyy"
DEFAULT_DECIMAL_STYLE: DecimalStyle = "dot_thousands"
MAPPING_FIELDS = ("date", "description", "amount", "debit", "credit")
FIELD_LABELS = {
    "date": "Ngày giao dịch",
    "description": "Nội dung",
    "amount": "Số tiền (+/−)",
    "debit": "Ghi nợ (tiền ra)",
    "credit": "Ghi có (tiền vào)",
}

# Tên cột thường gặp (đã bỏ dấu, chữ thường), **ưu tiên giảm dần** khi nhiều cột khớp nguyên tên
# (vd "Ngày giao dịch" > "Ngày" > "Ngày hiệu lực"). Alias ≤ 3 ký tự chỉ khớp nguyên tên cột.
# fmt: off
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "ngay giao dich", "ngay gd", "ngay thuc hien", "ngay gio giao dich", "thoi gian giao dich",
        "transaction date", "txn date", "trans date", "ngay", "ngay hach toan", "posting date",
        "date", "ngay hieu luc", "value date", "effective date", "thoi gian",
    ),
    "description": (
        "noi dung giao dich", "noi dung chi tiet", "noi dung chuyen khoan", "noi dung",
        "dien giai", "mo ta", "chi tiet giao dich", "chi tiet", "transaction details",
        "transaction description", "description", "details", "narrative", "remarks", "remark",
        "memo",
    ),
    "debit": (
        "so tien ghi no", "ghi no", "phat sinh no", "so tien no", "no", "tien ra", "so tien chi",
        "rut ra", "debit amount", "debit", "withdrawal", "withdrawals", "money out", "dr",
    ),
    "credit": (
        "so tien ghi co", "ghi co", "phat sinh co", "so tien co", "co", "tien vao", "so tien thu",
        "gui vao", "credit amount", "credit", "deposit", "deposits", "money in", "cr",
    ),
    "amount": (
        "so tien giao dich", "so tien", "gia tri giao dich", "gia tri", "transaction amount",
        "amount",
    ),
}
# Cột không map (số dư, mã tham chiếu…) — chỉ dùng để nhận ra dòng tiêu đề và chặn khớp nhầm.
IGNORED_ALIASES: tuple[str, ...] = (
    "so du", "so du cuoi", "balance", "running balance", "so tham chieu", "ma giao dich",
    "ma gd", "reference", "ref", "stt", "so but toan", "so tai khoan", "tai khoan", "account",
    "doi tac", "kenh giao dich",
)
# Nội dung có vẻ là chuyển tiền giữa các tài khoản của chính user (không phải thu / chi thật).
TRANSFER_PATTERNS: tuple[str, ...] = (
    "tra no the", "thanh toan the tin dung", "tt the tin dung", "thanh toan du no",
    "thanh toan sao ke the", "chuyen khoan noi bo", "chuyen tien noi bo", "ck noi bo",
    "chuyen sang tai khoan tiet kiem", "gui tiet kiem", "gui tien tiet kiem", "mo so tiet kiem",
    "tat toan", "rut tiet kiem", "nap tien vao vi", "nap vi", "credit card payment",
    "internal transfer", "own account transfer",
)
# fmt: on

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})(?:$|[\sT])")
_CURRENCY_RE = re.compile(r"(vnđ|vnd|đ|₫)", re.IGNORECASE)
_LONG_NUMBER_TOKEN_RE = re.compile(r"\S*\d\S*")
_EXCEL_EPOCH = date(1899, 12, 30)


# ---------- tiêu đề cột ----------


def normalize_header(text: str) -> str:
    """ "Số tiền ghi nợ (VND)" → "so tien ghi no vnd"."""
    return " ".join(_NON_WORD_RE.sub(" ", strip_accents(text).lower()).split())


def _alias_score(header: str, aliases: Sequence[str]) -> int:
    """Khớp nguyên tên cột: 2000 − thứ tự ưu tiên; tên cột chứa alias (nguyên từ): độ dài alias
    (cụ thể hơn thắng, vd "so tien ghi no" thắng "so tien")."""
    best = 0
    padded = f" {header} "
    for index, alias in enumerate(aliases):
        if header == alias:
            best = max(best, 2000 - index)
        elif len(alias) > 3 and f" {alias} " in padded:
            best = max(best, len(alias))
    return best


def field_scores(header: str) -> dict[str, int]:
    """Điểm khớp của một tên cột với từng trường (0 = không khớp; cột số dư… luôn 0)."""
    normalized = normalize_header(header)
    if not normalized:
        return dict.fromkeys(MAPPING_FIELDS, 0)
    ignored = _alias_score(normalized, IGNORED_ALIASES)
    scores = {}
    for name in MAPPING_FIELDS:
        score = _alias_score(normalized, FIELD_ALIASES[name])
        scores[name] = score if score > ignored else 0
    return scores


def _header_score(row: Sequence[str]) -> int:
    known = 0
    for cell in row:
        normalized = normalize_header(cell)
        if not normalized:
            continue
        if any(field_scores(cell).values()) or _alias_score(normalized, IGNORED_ALIASES):
            known += 1
    return known


def find_header_row(rows: Sequence[Sequence[str]]) -> int:
    """Chỉ số (từ 0) của dòng tiêu đề cột: dòng đầu tiên (trong 30 dòng đầu) có nhiều tên cột
    quen thuộc nhất (≥ 2); không có thì dòng đầu tiên nhiều ô có giá trị nhất."""
    scan = list(rows[:HEADER_SCAN_ROWS])
    best_index, best_score = -1, 1
    for index, row in enumerate(scan):
        score = _header_score(row)
        if score > best_score:
            best_index, best_score = index, score
    if best_index >= 0:
        return best_index
    filled = [sum(1 for cell in row if cell) for row in scan]
    if not filled or max(filled) == 0:
        return 0
    return filled.index(max(filled))


def label_headers(row: Sequence[str]) -> list[str]:
    """Tên cột hiển thị, duy nhất: ô trống → "Cột 3", trùng tên → "Số tiền (2)"."""
    labels: list[str] = []
    seen: Counter[str] = Counter()
    for index, cell in enumerate(row):
        label = _SPACE_RE.sub(" ", cell).strip() or f"Cột {index + 1}"
        seen[label] += 1
        labels.append(label if seen[label] == 1 else f"{label} ({seen[label]})")
    return labels


def headers_hash(headers: Sequence[str]) -> str:
    """sha256 của tên cột đã chuẩn hoá — khoá của mapping profile."""
    joined = "|".join(normalize_header(h) for h in headers)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def guess_mapping(headers: Sequence[str]) -> ColumnMapping:
    """Đoán mapping: mỗi trường lấy cột có điểm cao nhất, mỗi cột dùng 1 lần. Có ghi nợ / ghi có
    thì bỏ cột "số tiền"."""
    candidates = []
    for column, header in enumerate(headers):
        for name, score in field_scores(header).items():
            if score > 0:
                candidates.append((score, -column, name, header))
    candidates.sort(reverse=True)
    chosen: dict[str, str] = {}
    used: set[str] = set()
    for _, _, name, header in candidates:
        if name in chosen or header in used:
            continue
        chosen[name] = header
        used.add(header)
    if "debit" in chosen or "credit" in chosen:
        chosen.pop("amount", None)
    return ColumnMapping(**chosen)


def mapping_problems(mapping: ColumnMapping, headers: Sequence[str]) -> list[str]:
    """Lý do mapping chưa dùng được (rỗng = dùng được)."""
    problems = []
    values = mapping.model_dump()
    for name in MAPPING_FIELDS:
        column = values[name]
        if column and column not in headers:
            problems.append(f"Không có cột “{column}” trong file ({FIELD_LABELS[name]}).")
    if not mapping.date:
        problems.append("Chưa chọn cột ngày giao dịch.")
    if not mapping.description:
        problems.append("Chưa chọn cột nội dung giao dịch.")
    if not (mapping.amount or mapping.debit or mapping.credit):
        problems.append("Chưa chọn cột số tiền (hoặc cột ghi nợ / ghi có).")
    if mapping.amount and (mapping.debit or mapping.credit):
        problems.append("Chọn một cột số tiền (+/−) hoặc cột ghi nợ / ghi có, không chọn cả hai.")
    used = [v for v in values.values() if v]
    for column, count in Counter(used).items():
        if count > 1:
            problems.append(f"Cột “{column}” đang được chọn cho nhiều trường.")
    return problems


# ---------- ngày ----------


def guess_date_format(values: Iterable[str]) -> DateFormat:
    """Ngày đầu > 12 → dd/mm; phần thứ hai > 12 → mm/dd; năm đứng đầu → yyyy-mm-dd; mặc định
    dd/mm/yyyy (Việt Nam)."""
    dmy = mdy = ymd = 0
    for value in values:
        match = _DATE_RE.match(value.strip())
        if not match:
            continue
        first, second, _ = match.groups()
        if len(first) == 4:
            ymd += 1
        elif int(first) > 12:
            dmy += 1
        elif int(second) > 12:
            mdy += 1
    if mdy and not dmy:
        return "mm/dd/yyyy"
    if ymd and not (dmy or mdy):
        return "yyyy-mm-dd"
    return DEFAULT_DATE_FORMAT


def parse_date(value: str, date_format: DateFormat = DEFAULT_DATE_FORMAT) -> date:
    """ "21/10/2026", "21-10-26 14:35", "2026-10-21", "46316" (serial Excel) → date.
    Sai → `ValueError` với thông báo tiếng Việt."""
    text = value.strip()
    if not text:
        raise ValueError("Thiếu ngày giao dịch")
    if text.isdigit() and len(text) == 5:
        return _EXCEL_EPOCH + timedelta(days=int(text))
    match = _DATE_RE.match(text)
    if not match:
        raise ValueError(f"Ngày không hợp lệ: “{text}”")
    first, second, third = match.groups()
    if len(first) == 4:
        year, month, day = first, second, third
    elif date_format == "mm/dd/yyyy":
        month, day, year = first, second, third
    else:
        day, month, year = first, second, third
    if len(year) == 2:
        year = f"20{year}"
    if len(year) != 4:
        raise ValueError(f"Ngày không hợp lệ: “{text}”")
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        raise ValueError(f"Ngày không hợp lệ: “{text}”") from None


# ---------- số tiền ----------


def _clean_amount_text(value: str) -> tuple[str, bool]:
    """Bỏ khoảng trắng / ký hiệu tiền, nhận dấu âm `-x`, `x-`, `(x)`. Trả `(chuỗi số, âm?)`."""
    text = value.strip().replace("\u2212", "-").replace("\u00a0", "").replace(" ", "")
    text = _CURRENCY_RE.sub("", text)
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.startswith("-"):
        negative, text = not negative, text[1:]
    elif text.startswith("+"):
        text = text[1:]
    if text.endswith("-"):
        negative, text = not negative, text[:-1]
    return text, negative


def guess_decimal_style(values: Iterable[str]) -> DecimalStyle:
    """Kiểu dấu phân cách hàng nghìn của file, bỏ phiếu theo từng giá trị; hoà → dấu chấm (VN)."""
    dot = comma = 0
    for value in values:
        text, _ = _clean_amount_text(value)
        if not re.fullmatch(r"[\d.,]+", text or "x"):
            continue
        if "." in text and "," in text:
            if text.rfind(",") > text.rfind("."):
                dot += 1
            else:
                comma += 1
            continue
        for sep in (".", ","):
            if sep not in text:
                continue
            parts = text.split(sep)
            vote_thousands = len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3)
            vote_decimal = len(parts) == 2 and 1 <= len(parts[1]) <= 2
            if (sep == "." and vote_thousands) or (sep == "," and vote_decimal):
                dot += 1
            elif (sep == "," and vote_thousands) or (sep == "." and vote_decimal):
                comma += 1
    return "comma_thousands" if comma > dot else DEFAULT_DECIMAL_STYLE


def parse_amount(value: str, decimal_style: DecimalStyle = DEFAULT_DECIMAL_STYLE) -> int | None:
    """Số tiền có dấu (âm = tiền ra), làm tròn tới đồng; ô trống / "-" → `None`.
    Sai → `ValueError`."""
    original = value.strip()
    if original in {"", "-", "–", "—"}:
        return None
    text, negative = _clean_amount_text(original)
    if not text or not re.fullmatch(r"[\d.,]+", text) or not any(ch.isdigit() for ch in text):
        raise ValueError(f"Số tiền không hợp lệ: “{original}”")
    thousands_sep, decimal_sep = (".", ",") if decimal_style == "dot_thousands" else (",", ".")
    if "." in text and "," in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        integer, _, fraction = text.rpartition(decimal_sep)
        if decimal_sep in integer:
            raise ValueError(f"Số tiền không hợp lệ: “{original}”")
        digits = integer.replace(thousands_sep, "") + "." + fraction
    else:
        sep = "." if "." in text else ("," if "," in text else None)
        if sep is None:
            digits = text
        else:
            parts = text.split(sep)
            grouped = all(len(p) == 3 for p in parts[1:]) and 1 <= len(parts[0]) <= 3
            if len(parts) > 2:
                if not grouped:
                    raise ValueError(f"Số tiền không hợp lệ: “{original}”")
                digits = "".join(parts)
            elif 1 <= len(parts[1]) <= 2:
                digits = f"{parts[0]}.{parts[1]}"
            elif len(parts[1]) == 3 and sep == thousands_sep:
                digits = "".join(parts)
            elif sep == decimal_sep and parts[0] and parts[1]:
                digits = f"{parts[0]}.{parts[1]}"
            elif grouped:
                digits = "".join(parts)
            else:
                raise ValueError(f"Số tiền không hợp lệ: “{original}”")
    try:
        amount = round_vnd(Decimal(digits))
    except InvalidOperation:
        raise ValueError(f"Số tiền không hợp lệ: “{original}”") from None
    return -amount if negative else amount


# ---------- nội dung ----------


def display_description(text: str) -> str:
    """Nội dung hiển thị / ghi chú giao dịch: NFC, gọn khoảng trắng, ≤ 500 ký tự."""
    collapsed = _SPACE_RE.sub(" ", unicodedata.normalize("NFC", text)).strip()
    return collapsed[:MAX_NOTE_LENGTH]


def normalize_description(text: str) -> str:
    """Nội dung dùng để so trùng: chữ thường, NFC, gọn khoảng trắng (giữ nguyên tên cửa hàng)."""
    return display_description(text).lower()


def dedup_hash(occurred_on: date, amount: int, direction: str, normalized: str) -> str:
    key = f"{occurred_on.isoformat()}|{amount}|{direction}|{normalized}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def is_transfer_like(description: str) -> bool:
    """Chuyển khoản nội bộ / trả nợ thẻ / gửi tiết kiệm / nạp ví — không phải thu chi thật."""
    padded = f" {normalize_header(description)} "
    return any(f" {pattern} " in padded for pattern in TRANSFER_PATTERNS)


def prompt_safe_description(text: str) -> str:
    """Nội dung gửi cho model: che token có ≥ 5 chữ số (số tài khoản, mã giao dịch, số dư…)
    bằng `#`, ≤ 160 ký tự."""

    def mask(match: re.Match[str]) -> str:
        token = match.group(0)
        return "#" if sum(ch.isdigit() for ch in token) >= 5 else token

    masked = _LONG_NUMBER_TOKEN_RE.sub(mask, display_description(text))
    return masked[:MAX_PROMPT_NOTE_LENGTH]


# ---------- dòng ----------


@dataclass(frozen=True)
class ParsedRow:
    row_index: int
    raw: dict[str, str]
    occurred_on: date | None = None
    amount: int | None = None
    direction: str | None = None
    note: str = ""
    normalized: str = ""
    dedup_hash: str | None = None
    status: str = "valid"
    error: str | None = None
    duplicate_of_row: int | None = None
    duplicate_existing: bool = False
    transfer_hint: bool = False
    warnings: list[str] = field(default_factory=list)


def _cell(row: Sequence[str], headers: Sequence[str], column: str | None) -> str:
    if not column or column not in headers:
        return ""
    index = list(headers).index(column)
    return row[index] if index < len(row) else ""


def _direction_amount(
    raw: dict[str, str], mapping: ColumnMapping, decimal_style: DecimalStyle
) -> tuple[str, int]:
    if mapping.amount:
        value = parse_amount(raw.get("amount", ""), decimal_style)
        if not value:
            raise ValueError("Thiếu số tiền")
        return ("expense" if value < 0 else "income"), abs(value)
    debit = parse_amount(raw.get("debit", ""), decimal_style) if mapping.debit else None
    credit = parse_amount(raw.get("credit", ""), decimal_style) if mapping.credit else None
    if debit and credit:
        raise ValueError("Dòng có cả ghi nợ và ghi có")
    if debit:
        return "expense", abs(debit)
    if credit:
        return "income", abs(credit)
    raise ValueError("Thiếu số tiền (ghi nợ / ghi có đều trống)")


def parse_row(
    row_index: int,
    row: Sequence[str],
    headers: Sequence[str],
    mapping: ColumnMapping,
    date_format: DateFormat,
    decimal_style: DecimalStyle,
) -> ParsedRow:
    raw = {
        name: _cell(row, headers, getattr(mapping, name))
        for name in MAPPING_FIELDS
        if getattr(mapping, name)
    }
    description = raw.get("description", "")
    note = display_description(description)
    try:
        occurred_on = parse_date(raw.get("date", ""), date_format)
        direction, amount = _direction_amount(raw, mapping, decimal_style)
        if amount > MAX_AMOUNT:
            raise ValueError("Số tiền quá lớn")
    except ValueError as exc:
        return ParsedRow(row_index=row_index, raw=raw, note=note, status="bad", error=str(exc))
    normalized = normalize_description(description)
    return ParsedRow(
        row_index=row_index,
        raw=raw,
        occurred_on=occurred_on,
        amount=amount,
        direction=direction,
        note=note,
        normalized=normalized,
        dedup_hash=dedup_hash(occurred_on, amount, direction, normalized),
        transfer_hint=is_transfer_like(description),
    )


def data_rows(rows: Sequence[Sequence[str]], header_index: int) -> list[tuple[int, Sequence[str]]]:
    """Các dòng dữ liệu (sau dòng tiêu đề, bỏ dòng trống) kèm số thứ tự dòng trong file (từ 1)."""
    return [
        (index + 1, row)
        for index, row in enumerate(rows)
        if index > header_index and any(cell for cell in row)
    ]


def parse_rows(
    rows: Sequence[Sequence[str]],
    header_index: int,
    headers: Sequence[str],
    mapping: ColumnMapping,
    date_format: DateFormat,
    decimal_style: DecimalStyle,
    existing_hashes: Iterable[str] = (),
) -> list[ParsedRow]:
    """Chuẩn hoá mọi dòng dữ liệu + đánh dấu trùng. Mapping chưa đủ → mọi dòng `bad`."""
    problems = mapping_problems(mapping, headers)
    items = data_rows(rows, header_index)
    if problems:
        return [
            ParsedRow(
                row_index=index,
                raw={},
                note="",
                status="bad",
                error="Mapping cột chưa đủ: " + " ".join(problems),
            )
            for index, _ in items
        ]
    parsed = [
        parse_row(index, row, headers, mapping, date_format, decimal_style) for index, row in items
    ]
    return mark_duplicates(parsed, existing_hashes)


def mark_duplicates(rows: Sequence[ParsedRow], existing_hashes: Iterable[str]) -> list[ParsedRow]:
    """Dòng có hash đã import trước đó, hoặc trùng dòng trước trong file → `duplicate`."""
    existing = set(existing_hashes)
    first_seen: dict[str, int] = {}
    result = []
    for row in rows:
        if row.status == "bad" or row.dedup_hash is None:
            result.append(row)
            continue
        if row.dedup_hash in existing:
            result.append(
                replace(
                    row,
                    status="duplicate",
                    duplicate_existing=True,
                    error="Đã import dòng này trước đó",
                )
            )
        elif row.dedup_hash in first_seen:
            original = first_seen[row.dedup_hash]
            result.append(
                replace(
                    row,
                    status="duplicate",
                    duplicate_of_row=original,
                    error=f"Trùng dòng {original} trong file",
                )
            )
        else:
            first_seen[row.dedup_hash] = row.row_index
            result.append(row)
    return result


def column_values(
    rows: Sequence[Sequence[str]], header_index: int, headers: Sequence[str], column: str | None
) -> list[str]:
    return [_cell(row, headers, column) for _, row in data_rows(rows, header_index)]
