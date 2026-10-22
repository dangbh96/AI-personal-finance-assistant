"""Unit test import sao kê (Phase 14): đọc file, mapping, chuẩn hoá, dedup — không cần DB / AI."""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from app.core.errors import DomainError
from app.schemas.imports import ColumnMapping
from app.services import import_parsing as p
from app.services import import_reader as r

FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"


def _parse_file(name: str):
    content = (FIXTURES / name).read_bytes()
    table = r.read_table(content, name, "")
    header_index = p.find_header_row(table.rows)
    headers = p.label_headers(table.rows[header_index])
    mapping = p.guess_mapping(headers)
    date_format = p.guess_date_format(
        p.column_values(table.rows, header_index, headers, mapping.date)
    )
    values: list[str] = []
    for column in (mapping.amount, mapping.debit, mapping.credit):
        values += p.column_values(table.rows, header_index, headers, column)
    style = p.guess_decimal_style(values)
    rows = p.parse_rows(table.rows, header_index, headers, mapping, date_format, style)
    return table, headers, mapping, rows


# ---------- test case 1, 2: fixture ----------


@pytest.mark.parametrize(
    ("name", "encoding", "separator"),
    [
        ("vcb_statement.csv", "utf-8-sig", ";"),
        ("techcombank_statement.csv", "cp1258", ","),
        ("statement.xlsx", None, None),
    ],
)
def test_fixture_counts(name, encoding, separator):
    table, _, _, rows = _parse_file(name)
    assert table.encoding == encoding
    assert table.separator == separator
    counts = Counter(row.status for row in rows)
    assert len(rows) == 25
    assert counts == {"valid": 22, "duplicate": 2, "bad": 1}


def test_cp1258_decodes_vietnamese():
    _, _, _, rows = _parse_file("techcombank_statement.csv")
    notes = [row.note for row in rows]
    assert "Ăn trưa quán bún bò" in notes
    assert "Lương tháng 08/2026 công ty ABC" in notes
    assert not any("\ufffd" in note for note in notes)


def test_vcb_mapping_guessed_with_preamble():
    table, headers, mapping, _ = _parse_file("vcb_statement.csv")
    assert p.find_header_row(table.rows) == 3
    assert mapping == ColumnMapping(
        date="Ngày giao dịch",
        description="Nội dung chi tiết",
        debit="Số tiền ghi nợ",
        credit="Số tiền ghi có",
    )
    assert "Số dư" in headers


def test_xlsx_date_and_number_cells():
    table, _, mapping, rows = _parse_file("statement.xlsx")
    assert table.sheet_name == "Sao ke"
    assert mapping.debit == "Ghi nợ" and mapping.credit == "Ghi có"
    salary = rows[0]
    assert (salary.occurred_on, salary.amount, salary.direction) == (
        date(2026, 9, 1),
        25_000_000,
        "income",
    )


# ---------- đọc file ----------


def test_decode_csv_variants():
    text = "Ngày,Nội dung\n"
    assert r.decode_csv(text.encode("utf-8")) == (text, "utf-8")
    assert r.decode_csv(b"\xef\xbb\xbf" + text.encode("utf-8")) == (text, "utf-8-sig")
    decoded, encoding = r.decode_csv("Ăn trưa quán bún".encode("cp1258"))
    assert (decoded, encoding) == ("Ăn trưa quán bún", "cp1258")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a;b;c\n1;2;3\n", ";"),
        ("a,b,c\n1,2,3\n", ","),
        ("a\tb\tc\n1\t2\t3\n", "\t"),
        ('ngay,noi dung,so tien\n01/09/2026,"Cafe, banh",45.000\n', ","),
        ("ngay;noi dung;so tien\n01/09/2026;Cafe, banh, keo;1,500,000\n", ";"),
    ],
)
def test_sniff_separator(text, expected):
    assert r.sniff_separator(text) == expected


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "code", "status"),
    [
        ("sao-ke.xls", "", b"x", "unsupported_file_type", 415),
        ("sao-ke.pdf", "application/pdf", b"%PDF", "unsupported_file_type", 415),
        ("sao-ke.csv", "image/png", b"a,b", "unsupported_file_type", 415),
        ("sao-ke.xlsx", "", b"not a zip", "unsupported_file_type", 415),
        ("sao-ke.csv", "text/csv", b"a,b\x00\x00", "unsupported_file_type", 415),
        ("sao-ke.csv", "text/csv", b"", "empty_file", 422),
        ("sao-ke.csv", "text/csv", b"\n\n  \n", "empty_file", 422),
        ("sao-ke.xlsx", "", b"PK\x03\x04broken", "unreadable_file", 422),
    ],
)
def test_read_table_rejects(filename, content_type, content, code, status):
    with pytest.raises(DomainError) as exc:
        r.read_table(content, filename, content_type)
    assert exc.value.code == code
    assert exc.value.status_code == status


def test_read_table_too_large():
    with pytest.raises(DomainError) as exc:
        r.read_table(b"a" * (r.MAX_IMPORT_BYTES + 1), "x.csv", "text/csv")
    assert exc.value.status_code == 413


def test_read_table_too_many_rows():
    content = ("ngay,noi dung,so tien\n" + "01/09/2026,x,1\n" * (r.MAX_IMPORT_ROWS + 1)).encode()
    with pytest.raises(DomainError) as exc:
        r.read_table(content, "x.csv", "text/csv")
    assert exc.value.code == "too_many_rows"


def test_read_csv_ragged_rows_and_quotes():
    content = 'Sao kê\nNgày;Nội dung;Số tiền\n01/09/2026;"Cafe; bánh";-45.000\n;;;;\n'.encode()
    table = r.read_table(content, "x.csv", "application/vnd.ms-excel")
    assert table.rows[0] == ["Sao kê", "", "", "", ""]
    assert table.rows[2] == ["01/09/2026", "Cafe; bánh", "-45.000", "", ""]
    assert len(table.rows) == 3


def test_clean_filename_strips_directories():
    assert r.clean_filename("C:\\Users\\a\\sao ke.csv") == "sao ke.csv"
    assert r.clean_filename("../../etc/passwd.csv") == "passwd.csv"
    assert r.clean_filename(None) == "sao-ke.csv"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (25_000_000.0, "25000000"),
        (165000.00000000003, "165000"),
        (1234.567, "1234.57"),
        (-52000.0, "-52000"),
        (0.0, "0"),
        (float("nan"), ""),
        (None, ""),
        (date(2026, 9, 1), "2026-09-01"),
        ("  Ăn trưa ", "Ăn trưa"),
    ],
)
def test_clean_cell(value, expected):
    assert r.clean_cell(value) == expected


def test_excel_float_noise_parses_as_amount():
    assert p.parse_amount(r.clean_cell(165000.00000000003)) == 165_000
    assert p.parse_amount(r.clean_cell(1234.567)) == 1_235


# ---------- tiêu đề / mapping ----------


def test_find_header_row_fallback_without_known_names():
    rows = [["Bảng kê"], ["", ""], ["A", "B", "C"], ["1", "2", "3"]]
    assert p.find_header_row(rows) == 2


def test_label_headers_unique():
    assert p.label_headers(["Số tiền", "", "Số tiền", " Nội  dung "]) == [
        "Số tiền",
        "Cột 2",
        "Số tiền (2)",
        "Nội dung",
    ]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (
            ["Ngày", "Diễn giải", "Số tiền", "Số dư"],
            {"date": "Ngày", "description": "Diễn giải", "amount": "Số tiền"},
        ),
        (
            ["Transaction Date", "Description", "Debit", "Credit", "Balance"],
            {
                "date": "Transaction Date",
                "description": "Description",
                "debit": "Debit",
                "credit": "Credit",
            },
        ),
        (
            ["Ngày hiệu lực", "Ngày giao dịch", "Mô tả", "Phát sinh Nợ", "Phát sinh Có"],
            {
                "date": "Ngày giao dịch",
                "description": "Mô tả",
                "debit": "Phát sinh Nợ",
                "credit": "Phát sinh Có",
            },
        ),
        (
            ["Ngày GD", "Nội dung", "Số tiền", "Ghi nợ", "Ghi có"],
            {"date": "Ngày GD", "description": "Nội dung", "debit": "Ghi nợ", "credit": "Ghi có"},
        ),
        (["Cột A", "Cột B"], {}),
    ],
)
def test_guess_mapping(headers, expected):
    assert p.guess_mapping(headers).model_dump(exclude_none=True) == expected


def test_mapping_problems():
    headers = ["Ngày", "Nội dung", "Số tiền", "Ghi nợ"]
    assert (
        p.mapping_problems(
            ColumnMapping(date="Ngày", description="Nội dung", amount="Số tiền"), headers
        )
        == []
    )
    problems = p.mapping_problems(
        ColumnMapping(date="Ngày", amount="Số tiền", debit="Ghi nợ", credit="Không có"), headers
    )
    assert any("nội dung" in x for x in problems)
    assert any("Không có" in x for x in problems)
    assert any("không chọn cả hai" in x for x in problems)
    assert any(
        "nhiều trường" in x
        for x in p.mapping_problems(
            ColumnMapping(date="Ngày", description="Ngày", amount="Số tiền"), headers
        )
    )


def test_headers_hash_ignores_accents_and_case():
    assert p.headers_hash(["Ngày", "Số tiền"]) == p.headers_hash(["ngay", "SO TIEN"])
    assert p.headers_hash(["Ngày", "Số tiền"]) != p.headers_hash(["Ngày", "Nội dung"])


# ---------- ngày ----------


@pytest.mark.parametrize(
    ("value", "fmt", "expected"),
    [
        ("21/10/2026", "dd/mm/yyyy", date(2026, 10, 21)),
        ("21-10-26", "dd/mm/yyyy", date(2026, 10, 21)),
        ("21.10.2026 14:35:00", "dd/mm/yyyy", date(2026, 10, 21)),
        ("2026-10-21", "dd/mm/yyyy", date(2026, 10, 21)),
        ("2026-10-21T08:00:00", "dd/mm/yyyy", date(2026, 10, 21)),
        ("10/21/2026", "mm/dd/yyyy", date(2026, 10, 21)),
        ("46316", "dd/mm/yyyy", date(2026, 10, 21)),
    ],
)
def test_parse_date(value, fmt, expected):
    assert p.parse_date(value, fmt) == expected


@pytest.mark.parametrize("value", ["32/13/2026", "30/02/2026", "hôm qua", "", "1/2/326"])
def test_parse_date_invalid(value):
    with pytest.raises(ValueError):
        p.parse_date(value)


def test_guess_date_format():
    assert p.guess_date_format(["01/09/2026", "25/09/2026"]) == "dd/mm/yyyy"
    assert p.guess_date_format(["09/01/2026", "09/25/2026"]) == "mm/dd/yyyy"
    assert p.guess_date_format(["2026-09-01"]) == "yyyy-mm-dd"
    assert p.guess_date_format(["01/02/2026"]) == "dd/mm/yyyy"


# ---------- số tiền (test case 3) ----------


@pytest.mark.parametrize(
    ("value", "style", "expected"),
    [
        ("1.500.000", "dot_thousands", 1_500_000),
        ("1,500,000", "dot_thousands", 1_500_000),
        ("1,500,000.00", "comma_thousands", 1_500_000),
        ("1.500.000,00", "dot_thousands", 1_500_000),
        ("1500000.00", "dot_thousands", 1_500_000),
        ("45.000", "dot_thousands", 45_000),
        ("45,000", "comma_thousands", 45_000),
        ("-1.500.000", "dot_thousands", -1_500_000),
        ("(1.500.000)", "dot_thousands", -1_500_000),
        ("1.500.000-", "dot_thousands", -1_500_000),
        ("−52.000", "dot_thousands", -52_000),
        ("+25.000.000", "dot_thousands", 25_000_000),
        ("1.500.000 VND", "dot_thousands", 1_500_000),
        ("1.500.000đ", "dot_thousands", 1_500_000),
        ("25000000", "dot_thousands", 25_000_000),
        ("1 500 000", "dot_thousands", 1_500_000),
        ("12500.5", "dot_thousands", 12_501),
        ("", "dot_thousands", None),
        ("-", "dot_thousands", None),
    ],
)
def test_parse_amount(value, style, expected):
    assert p.parse_amount(value, style) == expected


@pytest.mark.parametrize("value", ["abc", "1.5000", "12,34,56", "1.2.3,4.5"])
def test_parse_amount_invalid(value):
    with pytest.raises(ValueError):
        p.parse_amount(value)


def test_guess_decimal_style():
    assert p.guess_decimal_style(["1.500.000", "45.000", ""]) == "dot_thousands"
    assert p.guess_decimal_style(["1,500,000.00", "45,000"]) == "comma_thousands"
    assert p.guess_decimal_style(["45,000", "120,000"]) == "comma_thousands"
    assert p.guess_decimal_style(["25000000"]) == "dot_thousands"


# ---------- chiều tiền / dòng ----------

HEADERS_DC = ["Ngày", "Nội dung", "Ghi nợ", "Ghi có"]
MAP_DC = ColumnMapping(date="Ngày", description="Nội dung", debit="Ghi nợ", credit="Ghi có")
HEADERS_AMOUNT = ["Ngày", "Nội dung", "Số tiền"]
MAP_AMOUNT = ColumnMapping(date="Ngày", description="Nội dung", amount="Số tiền")


def _row(cells, headers=HEADERS_DC, mapping=MAP_DC):
    return p.parse_row(7, cells, headers, mapping, "dd/mm/yyyy", "dot_thousands")


def test_debit_is_expense_credit_is_income():
    debit = _row(["03/09/2026", "Tiền điện", "1.500.000", ""])
    assert (debit.direction, debit.amount, debit.status) == ("expense", 1_500_000, "valid")
    credit = _row(["01/09/2026", "LUONG T8", "", "25.000.000"])
    assert (credit.direction, credit.amount) == ("income", 25_000_000)
    negative_debit = _row(["03/09/2026", "x", "-52.000", ""])
    assert (negative_debit.direction, negative_debit.amount) == ("expense", 52_000)


def test_signed_amount_column():
    expense = _row(["03/09/2026", "x", "-45.000"], HEADERS_AMOUNT, MAP_AMOUNT)
    income = _row(["03/09/2026", "x", "3.000.000"], HEADERS_AMOUNT, MAP_AMOUNT)
    assert (expense.direction, expense.amount) == ("expense", 45_000)
    assert (income.direction, income.amount) == ("income", 3_000_000)


@pytest.mark.parametrize(
    ("cells", "error"),
    [
        (["32/13/2026", "x", "11.000", ""], "Ngày không hợp lệ"),
        (["03/09/2026", "x", "", ""], "Thiếu số tiền"),
        (["03/09/2026", "x", "0", "0"], "Thiếu số tiền"),
        (["03/09/2026", "x", "10.000", "20.000"], "cả ghi nợ và ghi có"),
        (["03/09/2026", "x", "abc", ""], "Số tiền không hợp lệ"),
        (["", "x", "10.000", ""], "Thiếu ngày"),
    ],
)
def test_bad_rows(cells, error):
    row = _row(cells)
    assert row.status == "bad"
    assert error in row.error
    assert row.dedup_hash is None


def test_incomplete_mapping_marks_every_row_bad():
    rows = p.parse_rows(
        [HEADERS_DC, ["03/09/2026", "x", "1", ""]],
        0,
        HEADERS_DC,
        ColumnMapping(date="Ngày"),
        "dd/mm/yyyy",
        "dot_thousands",
    )
    assert [(row.status, row.error.startswith("Mapping cột chưa đủ")) for row in rows] == [
        ("bad", True)
    ]


# ---------- dedup (test case 5) ----------


def test_normalize_description():
    assert p.normalize_description("  GRAB*TRIP   1234\tHCM ") == "grab*trip 1234 hcm"
    assert p.normalize_description("Ăn  Trưa") == "ăn trưa"


def test_same_row_same_hash_later_is_duplicate():
    table = [
        HEADERS_DC,
        ["05/09/2026", "HIGHLANDS COFFEE", "59.000", ""],
        ["05/09/2026", "highlands  coffee ", "59.000", ""],
        ["05/09/2026", "HIGHLANDS COFFEE", "59.000", ""],
        ["06/09/2026", "HIGHLANDS COFFEE", "59.000", ""],
        ["05/09/2026", "HIGHLANDS COFFEE", "", "59.000"],
    ]
    rows = p.parse_rows(table, 0, HEADERS_DC, MAP_DC, "dd/mm/yyyy", "dot_thousands")
    assert rows[0].dedup_hash == rows[1].dedup_hash == rows[2].dedup_hash
    assert [row.status for row in rows] == ["valid", "duplicate", "duplicate", "valid", "valid"]
    assert rows[1].duplicate_of_row == 2
    assert len({rows[0].dedup_hash, rows[3].dedup_hash, rows[4].dedup_hash}) == 3


def test_existing_hash_is_duplicate():
    table = [HEADERS_DC, ["05/09/2026", "CAFE", "59.000", ""]]
    first = p.parse_rows(table, 0, HEADERS_DC, MAP_DC, "dd/mm/yyyy", "dot_thousands")
    again = p.parse_rows(
        table,
        0,
        HEADERS_DC,
        MAP_DC,
        "dd/mm/yyyy",
        "dot_thousands",
        existing_hashes={first[0].dedup_hash},
    )
    assert again[0].status == "duplicate" and again[0].duplicate_existing


def test_dedup_hash_is_stable():
    expected = p.dedup_hash(date(2026, 9, 5), 59_000, "expense", "cafe")
    assert expected == p.dedup_hash(date(2026, 9, 5), 59_000, "expense", "cafe")
    assert len(expected) == 64


# ---------- chuyển khoản nội bộ / nội dung gửi model ----------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("THANH TOAN THE TIN DUNG VISA", True),
        ("Trả nợ thẻ tín dụng tháng 9", True),
        ("Chuyển khoản nội bộ sang TK tiết kiệm", True),
        ("GUI TIET KIEM ONLINE 6 THANG", True),
        ("Nạp tiền vào ví MoMo", True),
        ("CK cho Nam tiền ăn", False),
        ("GRAB*TRIP HCM", False),
    ],
)
def test_is_transfer_like(text, expected):
    assert p.is_transfer_like(text) is expected


def test_prompt_safe_description_masks_long_numbers():
    text = "CK DEN 0001234567890 FT26245123456 TIEN NHA T9 SO DU 12.345.678"
    safe = p.prompt_safe_description(text)
    assert "0001234567890" not in safe
    assert "FT26245123456" not in safe
    assert "12.345.678" not in safe
    assert "TIEN NHA T9" in safe
    assert p.prompt_safe_description("GRAB*TRIP 1234 HCM") == "GRAB*TRIP 1234 HCM"
    assert len(p.prompt_safe_description("x" * 400)) == p.MAX_PROMPT_NOTE_LENGTH
