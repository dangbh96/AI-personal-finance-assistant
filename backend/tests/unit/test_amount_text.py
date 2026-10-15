import pytest

from app.services.amount_text import extract_amounts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hôm nay ăn phở 55k", [55_000]),
        ("Grab về nhà 45 nghìn", [45_000]),
        ("Gửi xe 5 ngàn", [5_000]),
        ("Tháng này nhận lương 25 triệu", [25_000_000]),
        ("Mua tai nghe 1tr5", [1_500_000]),
        ("Mua tai nghe 1.5tr", [1_500_000]),
        ("Mua tai nghe 1,5 triệu", [1_500_000]),
        ("Nhận freelance 4 triệu rưỡi", [4_500_000]),
        ("cơm 55 nghìn rưỡi", [55_500]),
        ("Học phí 1tr250", [1_250_000]),
        ("cafe 2 lít", [200_000]),
        ("Được thưởng dự án 3 củ", [3_000_000]),
        ("Sửa laptop 1.2tr", [1_200_000]),
        ("Mua xe 1 tỷ", [1_000_000_000]),
        ("Thu nhập 25m", [25_000_000]),
        ("Tiền điện 780.000đ", [780_000]),
        ("Tiền nhà 5.000.000 đồng", [5_000_000]),
        ("Tiền nước 120000", [120_000]),
        ("Sáng cafe 35k, trưa phở 55k, tối Grab 90k", [35_000, 55_000, 90_000]),
        ("2kg táo 80k", [80_000]),
        ("ĐI KHÁM 650 NGHÌN", [650_000]),
    ],
)
def test_extract_amounts(text, expected):
    assert extract_amounts(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "ăn phở",
        "Thứ 7 tuần trước mua 2 ly trà sữa",
        "tiết kiệm năm 2026",
        "ngày 07/10/2026 đi chợ",
        "lúc 10:30 ăn sáng",
        "0k",
    ],
)
def test_extract_amounts_ignores_non_money_numbers(text):
    assert extract_amounts(text) == []


def test_extract_amounts_returns_integers_without_float_error():
    # 1.15 × 1_000_000 bằng float = 1149999.9999999998
    assert extract_amounts("1.15tr") == [1_150_000]
    assert all(isinstance(v, int) for v in extract_amounts("1,1 triệu 2.3tr"))
