import pytest

from app.services.amount_text import amount_spans, remove_amounts
from app.services.classification_text import (
    extract_keyword,
    has_digits_besides_amounts,
    is_specific,
    normalize_pattern,
    normalize_text,
    overlap,
    pattern_matches,
    tokenize,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mua giày MLB 1.8 triệu", "mua giay mlb"),  # test case #1
        ("Grab về nhà 45 nghìn", "grab ve nha"),  # test case #2
        ("Mua giày Nike 2tr", "mua giay nike"),
        ("cafe 2 lít", "cafe"),
        ("Đặt giày Adidas 1tr2", "dat giay adidas"),
        ("Sửa màn hình laptop 900k!", "sua man hinh laptop"),
        ("Phở bò 55.000đ", "pho bo"),
        ("Tiền điện 1.250.000 vnđ", "tien dien"),
        ("Ăn sáng 2 ổ bánh mì 30k", "an sang banh mi"),
        ("  ", ""),
    ],
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


def test_normalize_text_removes_amount_tokens():
    normalized = normalize_text("Mua giày MLB 1.8 triệu")
    assert "1.8" not in normalized
    assert "trieu" not in normalized


def test_normalize_text_decomposed_unicode():
    """Câu gõ bằng bộ gõ tạo Unicode tổ hợp (NFD) vẫn chuẩn hoá như NFC."""
    import unicodedata

    assert normalize_text(unicodedata.normalize("NFD", "Mua giày 2tr")) == "mua giay"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mua giày MLB 1.8 triệu", "giay"),
        ("Cafe với khách 200k", "cafe"),
        ("Sửa laptop 900k", "sua laptop"),
        ("Tiền nhà tháng 10", "tien nha"),
        ("Grab về nhà 45k", "grab"),
        ("Nhận lương 25 triệu", "luong"),
        ("Hôm nay ăn phở 55k", "pho"),
        ("mua 50k", None),
        ("Tiền 100k", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_keyword(text, expected):
    assert extract_keyword(text) == expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("giày", "giay"),
        ("Sửa Laptop", "sua laptop"),
        ("cafe với khách", "cafe khach"),
        ("mua", ""),
    ],
)
def test_normalize_pattern(pattern, expected):
    assert normalize_pattern(pattern) == expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("giay", True),
        ("sua laptop", True),
        ("mua", False),  # test case #8: pattern quá rộng
        ("tien", False),
        ("sua", False),
        ("mua an", False),
        ("", False),
    ],
)
def test_is_specific(pattern, expected):
    assert is_specific(pattern) is expected


def test_pattern_matches_all_tokens_any_order():
    tokens = set(tokenize("sửa màn hình laptop 900k"))
    assert pattern_matches("sua laptop", tokens)
    assert not pattern_matches("sua xe", tokens)
    assert not pattern_matches("", tokens)
    assert not pattern_matches("giay", set(tokenize("Mua áo 450k")))


def test_overlap_ignores_stopwords():
    tokens = set(tokenize("mua giày thể thao"))
    assert overlap("giay nike", tokens) == 1
    assert overlap("mua", tokens) == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mua giày 2tr", False),
        ("Mua giày 2tr ngày 5/10", True),
        ("cafe lúc 7h 35k", True),
        ("2 ly cafe 50k", True),
    ],
)
def test_has_digits_besides_amounts(text, expected):
    assert has_digits_besides_amounts(text) is expected


def test_amount_spans_include_currency_suffix():
    normalized = "pho 55.000d, cafe 35k"
    spans = amount_spans(normalized)
    assert [normalized[s:e].strip() for s, e in spans] == ["55.000d", "35k"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mua giày Nike 2tr", "Mua giày Nike"),
        ("Phở bò 55.000đ ngon", "Phở bò ngon"),
        ("cafe 2 lít", "cafe"),
        ("Không có tiền", "Không có tiền"),
    ],
)
def test_remove_amounts_keeps_accents(text, expected):
    assert remove_amounts(text) == expected
