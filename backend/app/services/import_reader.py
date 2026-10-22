"""Đọc file sao kê CSV / XLSX thành bảng chuỗi (Phase 14) — deterministic, không AI.

- Chỉ nhận `.csv` / `.xlsx`, ≤ 10 MB, ≤ `MAX_IMPORT_ROWS` dòng dữ liệu; kiểm tra nội dung thật
  (XLSX phải là file zip, CSV không chứa byte NUL).
- CSV: thử `utf-8-sig` / `utf-8`, rồi `cp1258` (windows-1258, sao kê xuất từ phần mềm cũ); đoán dấu
  phân cách `,` / `;` / tab theo số cột ổn định nhất; đọc bằng `pandas`.
- XLSX: `pandas` + `openpyxl`, sheet đầu tiên có dữ liệu; ô ngày → `YYYY-MM-DD`, ô số → chuỗi số.
- Mọi ô được chuẩn hoá NFC + bỏ khoảng trắng hai đầu. Dòng trống hoàn toàn được giữ (đánh số dòng
  đúng như trong file); bộ phân tích bỏ qua sau.
"""

import csv
import io
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from app.core.errors import DomainError

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
MAX_FILENAME_LENGTH = 255
SNIFF_LINES = 50

ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx"})
# Trình duyệt gửi CSV với nhiều type khác nhau (Windows có Excel: application/vnd.ms-excel).
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "",
        "application/octet-stream",
        "text/csv",
        "text/plain",
        "text/x-csv",
        "application/csv",
        "application/x-csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
CSV_ENCODINGS = ("utf-8-sig", "cp1258")
SEPARATORS = (",", ";", "\t")
SEPARATOR_LABELS = {",": "dấu phẩy (,)", ";": "dấu chấm phẩy (;)", "\t": "tab"}

_ZIP_MAGIC = b"PK\x03\x04"


class ImportFileTooLarge(DomainError):
    status_code = 413

    def __init__(self) -> None:
        super().__init__(
            "File sao kê vượt quá dung lượng tối đa 10MB. Bạn tách file theo tháng giúp nhé.",
            "file_too_large",
        )


class UnsupportedImportFile(DomainError):
    status_code = 415

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "Chỉ nhận file sao kê .csv hoặc .xlsx (tối đa 10MB).",
            "unsupported_file_type",
        )


@dataclass(frozen=True)
class ReadTable:
    """Bảng thô: `rows[i]` là dòng thứ `i + 1` của file / sheet (mọi ô là chuỗi)."""

    file_type: str  # "csv" | "xlsx"
    rows: list[list[str]]
    encoding: str | None = None
    separator: str | None = None
    sheet_name: str | None = None
    warnings: list[str] = field(default_factory=list)


def clean_filename(filename: str | None) -> str:
    """Chỉ giữ tên file (bỏ thư mục, cả kiểu Windows), cắt ≤ 255 ký tự."""
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "sao-ke.csv")[:MAX_FILENAME_LENGTH]


def extension_of(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def check_declared_type(content_type: str | None, filename: str) -> str:
    """Kiểm tra trước khi đọc nội dung (đuôi file + content type). Trả đuôi file."""
    extension = extension_of(filename)
    if extension == ".xls":
        raise UnsupportedImportFile(
            "File Excel cũ (.xls) chưa được hỗ trợ — bạn mở file và lưu lại dạng .xlsx hoặc .csv "
            "giúp nhé."
        )
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedImportFile()
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedImportFile()
    return extension


def clean_cell(value: Any) -> str:
    """Giá trị ô → chuỗi đã chuẩn hoá (ngày ISO, số nguyên không có `.0`)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        # Ô số của Excel hay có sai số nhị phân (165000.00000000003) → làm tròn 2 chữ số lẻ, bỏ số 0
        # thừa; dấu `.` + ≤ 2 chữ số luôn được `parse_amount` hiểu là phần thập phân.
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return "0" if text in {"", "-0"} else text
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    text = str(value)
    if text.lower() in {"nan", "nat"}:
        return ""
    return unicodedata.normalize("NFC", text).strip()


def decode_csv(content: bytes) -> tuple[str, str]:
    """Giải mã CSV: `utf-8-sig` (có / không BOM) rồi `cp1258`. Trả `(text, encoding)`."""
    for encoding in CSV_ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        label = encoding
        if encoding == "utf-8-sig" and not content.startswith(b"\xef\xbb\xbf"):
            label = "utf-8"
        # cp1258 dùng dấu thanh tổ hợp → NFC để "a" + dấu sắc thành "á".
        return unicodedata.normalize("NFC", text), label
    raise DomainError(
        "Không đọc được bảng mã của file CSV — bạn lưu lại file dạng UTF-8 giúp nhé.",
        "unsupported_encoding",
    )


def _column_counts(lines: list[str], separator: str) -> list[int]:
    reader = csv.reader(lines, delimiter=separator)
    try:
        return [len(row) for row in reader if any(cell.strip() for cell in row)]
    except csv.Error:
        return []


def sniff_separator(text: str) -> str:
    """Dấu phân cách cho số cột ổn định nhất (> 1 cột) trong các dòng đầu; mặc định `,`."""
    lines = [line for line in text.splitlines() if line.strip()][:SNIFF_LINES]
    best: tuple[int, int, int] | None = None
    best_sep = ","
    for priority, separator in enumerate(SEPARATORS):
        counts = _column_counts(lines, separator)
        if not counts:
            continue
        columns, frequency = Counter(counts).most_common(1)[0]
        if columns < 2:
            continue
        # Nhiều dòng cùng số cột nhất, rồi nhiều cột hơn, rồi thứ tự ưu tiên.
        score = (frequency, columns, -priority)
        if best is None or score > best:
            best, best_sep = score, separator
    return best_sep


def _read_csv(content: bytes) -> ReadTable:
    if b"\x00" in content[:4096]:
        raise UnsupportedImportFile("Nội dung file không phải văn bản CSV hợp lệ.")
    text, encoding = decode_csv(content)
    separator = sniff_separator(text)
    lines = text.splitlines()
    try:
        width = max((len(row) for row in csv.reader(lines, delimiter=separator)), default=1)
    except csv.Error as exc:
        raise DomainError(
            "Không đọc được nội dung CSV (dòng có dấu ngoặc kép không đóng?).", "unreadable_file"
        ) from exc

    import pandas as pd

    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=separator,
            header=None,
            names=list(range(width)),
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=False,
            engine="python",
        )
    except Exception as exc:  # pandas raise nhiều loại lỗi parser khác nhau.
        raise DomainError(
            "Không đọc được nội dung CSV (dòng có dấu ngoặc kép không đóng?).", "unreadable_file"
        ) from exc
    rows = [[clean_cell(v) for v in row] for row in frame.astype(object).values.tolist()]
    return ReadTable(file_type="csv", rows=rows, encoding=encoding, separator=separator)


def _read_xlsx(content: bytes) -> ReadTable:
    if not content.startswith(_ZIP_MAGIC):
        raise UnsupportedImportFile("Nội dung file không phải bảng tính .xlsx hợp lệ.")

    import pandas as pd

    try:
        sheets = pd.read_excel(
            io.BytesIO(content), sheet_name=None, header=None, dtype=object, engine="openpyxl"
        )
    except Exception as exc:  # zip hỏng, thiếu phần XML, file có mật khẩu…
        raise DomainError(
            "Không đọc được file Excel — file hỏng hoặc đang đặt mật khẩu.", "unreadable_file"
        ) from exc
    warnings = []
    chosen: tuple[str, list[list[str]]] | None = None
    for name, frame in sheets.items():
        rows = [[clean_cell(v) for v in row] for row in frame.astype(object).values.tolist()]
        if any(any(cell for cell in row) for row in rows):
            if chosen is None:
                chosen = (str(name), rows)
            else:
                warnings.append(
                    f"File có nhiều sheet — chỉ đọc sheet đầu tiên có dữ liệu “{chosen[0]}”."
                )
                break
    if chosen is None:
        return ReadTable(file_type="xlsx", rows=[], sheet_name=None)
    return ReadTable(file_type="xlsx", rows=chosen[1], sheet_name=chosen[0], warnings=warnings)


def read_table(content: bytes, filename: str, content_type: str | None) -> ReadTable:
    """Validate + đọc file (đã đọc tối đa `MAX_IMPORT_BYTES + 1` byte). Lỗi → 413 / 415 / 422."""
    extension = check_declared_type(content_type, filename)
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportFileTooLarge()
    if not content:
        raise DomainError("File rỗng.", "empty_file")
    table = _read_csv(content) if extension == ".csv" else _read_xlsx(content)
    while table.rows and not any(table.rows[-1]):
        table.rows.pop()
    if not table.rows:
        raise DomainError("File không có dòng dữ liệu nào.", "empty_file")
    # +1: dòng tiêu đề cột (dòng mở đầu như tên ngân hàng / số tài khoản cũng được tính).
    if sum(1 for row in table.rows if any(row)) > MAX_IMPORT_ROWS + 1:
        limit = f"{MAX_IMPORT_ROWS:,}".replace(",", ".")
        raise DomainError(
            f"File có quá nhiều dòng (tối đa {limit} dòng mỗi lần) — bạn tách file theo tháng "
            "giúp nhé.",
            "too_many_rows",
        )
    return table
