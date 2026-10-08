import pytest

from app.core.text import slugify, strip_accents


def test_strip_accents():
    assert strip_accents("Thú cưng Đỏ đẹp") == "Thu cung Do dep"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Thú cưng", "thu_cung"),
        ("Quà tặng & hiếu hỉ", "qua_tang_hieu_hi"),
        ("  Điện   tử  ", "dien_tu"),
        ("Sức khoẻ", "suc_khoe"),
        ("Cà phê 2024!", "ca_phe_2024"),
        ("🐶", ""),
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected
