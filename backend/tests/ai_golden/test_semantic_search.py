"""Golden test semantic search (Phase 15) — OpenAI Embeddings thật: `pytest -m ai -s`.

Bộ dữ liệu 40 giao dịch tiếng Việt (ghi chú tự nhiên + vài dòng kiểu sao kê) tạo qua API trên DB
test (rollback sau test) → embed thật bằng `OPENAI_EMBEDDING_MODEL`. Ngưỡng:
- "ăn ngoài": nhà hàng / quán nướng / bún chả nằm top 10, precision@10 ≥ 0.70;
- "đi lại": grab / đổ xăng / vé xe bus nằm top 10, precision@10 ≥ 0.70;
- "Highlands": dòng Highlands ở top 3;
- lọc tháng 9 không trả dòng ngoài tháng 9.
"""

import sys

import pytest

from app.ai import openai_client

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

TX_URL = "/api/v1/transactions"
URL = "/api/v1/search/transactions"
PRECISION_THRESHOLD = 0.70

# (khoá, ghi chú, số tiền, ngày, slug danh mục, nhóm liên quan)
DATASET: list[tuple[str, str, int, str, str, str]] = [
    # ăn ngoài
    ("nha_hang", "Nhà hàng hải sản Biển Đông với gia đình", 850_000, "2026-10-04", "food", "eat"),
    ("quan_nuong", "Quán nướng Gò Vấp cùng team", 420_000, "2026-10-08", "food", "eat"),
    ("bun_cha", "Bún chả Hàng Mành", 45_000, "2026-10-12", "food", "eat"),
    ("lau", "Lẩu Thái quán Kichi", 320_000, "2026-10-15", "food", "eat"),
    ("pho", "Phở Thìn ăn sáng", 60_000, "2026-10-02", "food", "eat"),
    ("com_tam", "Cơm tấm sườn bì chả trưa", 55_000, "2026-10-06", "food", "eat"),
    ("sushi", "Sushi Tei sinh nhật bạn", 680_000, "2026-10-18", "food", "eat"),
    ("pizza", "Pizza 4P's tối thứ 7", 540_000, "2026-10-11", "food", "eat"),
    ("banh_mi", "Bánh mì Huỳnh Hoa", 70_000, "2026-10-09", "food", "eat"),
    ("bun_bo", "Ăn trưa quán bún bò Huế", 50_000, "2026-10-13", "food", "eat"),
    ("nha_hang_sep", "Nhà hàng chay Hương Sen", 380_000, "2026-09-18", "food", "eat"),
    ("shopee_food", "ShopeeFood đặt cơm gà", 75_000, "2026-10-16", "food", "eat"),
    # đi lại
    ("grab", "Grab về nhà", 85_000, "2026-10-06", "transport", "move"),
    ("xang", "Đổ xăng xe máy", 70_000, "2026-10-09", "transport", "move"),
    ("bus", "Vé xe bus tháng", 200_000, "2026-10-01", "transport", "move"),
    ("taxi", "Taxi Mai Linh ra sân bay", 250_000, "2026-10-17", "transport", "move"),
    ("gui_xe", "Gửi xe chung cư tháng 10", 120_000, "2026-10-01", "transport", "move"),
    ("be", "Be bike đi làm", 32_000, "2026-10-07", "transport", "move"),
    ("tau", "Vé tàu Sài Gòn - Nha Trang", 650_000, "2026-10-20", "transport", "move"),
    ("grab_sk", "THANH TOAN GRAB*TRIP 99231 HCM", 64_000, "2026-10-14", "transport", "move"),
    ("metro", "Thẻ metro Bến Thành - Suối Tiên", 300_000, "2026-10-03", "transport", "move"),
    ("rua_xe", "Rửa xe máy", 40_000, "2026-10-19", "transport", "move"),
    # cà phê
    ("highlands", "Cà phê Highlands Landmark", 59_000, "2026-10-10", "food", "coffee"),
    ("cafe_coc", "Cafe sữa đá cóc", 20_000, "2026-10-11", "food", "coffee"),
    ("tra_sua", "Trà sữa Phúc Long", 65_000, "2026-10-05", "food", "coffee"),
    ("starbucks", "Starbucks latte", 95_000, "2026-10-21", "food", "coffee"),
    # gây nhiễu
    ("cho", "Đi chợ mua rau thịt cá", 230_000, "2026-10-03", "food", "grocery"),
    ("sieu_thi", "Siêu thị Co.opmart mua đồ dùng", 640_000, "2026-10-12", "food", "grocery"),
    ("tien_nha", "Tiền thuê nhà tháng 10", 6_000_000, "2026-10-01", "housing", "other"),
    ("dien", "Tiền điện EVN tháng 9", 780_000, "2026-10-05", "utilities", "other"),
    ("internet", "Cước internet Viettel", 220_000, "2026-10-05", "utilities", "other"),
    ("thuoc", "Mua thuốc cảm Long Châu", 150_000, "2026-10-08", "health", "other"),
    ("giay", "Mua giày chạy bộ Nike", 2_100_000, "2026-10-14", "shopping", "other"),
    ("ao", "Áo sơ mi Uniqlo", 590_000, "2026-10-16", "shopping", "other"),
    ("netflix", "Netflix gói Premium", 260_000, "2026-10-02", "entertainment", "other"),
    ("phim", "Xem phim CGV", 180_000, "2026-10-18", "entertainment", "other"),
    ("sach", "Sách lập trình Python", 320_000, "2026-10-10", "education", "other"),
    ("qua", "Quà cưới đồng nghiệp", 1_000_000, "2026-10-19", "gifts", "other"),
    ("laptop", "Sạc laptop Dell", 450_000, "2026-10-07", "electronics", "other"),
    ("luong", "Lương tháng 10", 25_000_000, "2026-10-01", "salary", "income"),
]


def _report(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


@pytest.fixture
def categories(client) -> dict[str, dict]:
    return {c["slug"]: c for c in client.get("/api/v1/categories").json()}


@pytest.fixture
def seeded(client, categories) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for key, note, amount, day, slug, group in DATASET:
        category = categories[slug]
        resp = client.post(
            TX_URL,
            json={
                "direction": category["kind"],
                "amount": amount,
                "occurred_on": day,
                "category_id": category["id"],
                "note": note,
            },
        )
        assert resp.status_code == 201, resp.text
        rows[key] = {**resp.json(), "group": group}
    missing = client.get(URL, params={"q": "kiểm tra"}).json()["missing_embedding_count"]
    assert missing == 0, "Embedding thật lỗi khi tạo giao dịch"
    return rows


def _run(client, seeded, q: str, **params) -> list[dict]:
    resp = client.get(URL, params={"q": q, "limit": 10, **params})
    assert resp.status_code == 200, resp.text
    by_id = {v["id"]: k for k, v in seeded.items()}
    results = resp.json()["results"]
    _report(f"\n[{q}] {params or ''}")
    for r in results:
        key = by_id[r["transaction_id"]]
        _report(
            f"  {r['score']:.3f} sem={r['semantic_score']} kw={r['keyword_boost']} "
            f"{r['match_reason']:8} {seeded[key]['group']:8} {r['note']}"
        )
    return [{**r, "key": by_id[r["transaction_id"]]} for r in results]


def _precision(results: list[dict], seeded: dict, group: str) -> float:
    top = results[:10]
    assert len(top) >= 3
    return sum(1 for r in top if seeded[r["key"]]["group"] == group) / len(top)


def test_eating_out(client, seeded):
    results = _run(client, seeded, "ăn ngoài")
    keys = [r["key"] for r in results[:10]]
    for key in ("nha_hang", "quan_nuong", "bun_cha"):
        assert key in keys
    precision = _precision(results, seeded, "eat")
    _report(f"  precision@10 = {precision:.2f}")
    assert precision >= PRECISION_THRESHOLD


def test_travel(client, seeded):
    results = _run(client, seeded, "đi lại")
    keys = [r["key"] for r in results[:10]]
    for key in ("grab", "xang", "bus"):
        assert key in keys
    precision = _precision(results, seeded, "move")
    _report(f"  precision@10 = {precision:.2f}")
    assert precision >= PRECISION_THRESHOLD


def test_highlands_keyword_top3(client, seeded):
    results = _run(client, seeded, "Highlands")
    assert "highlands" in [r["key"] for r in results[:3]]


def test_date_filter_september(client, seeded):
    results = _run(client, seeded, "ăn ngoài", **{"from": "2026-09-01", "to": "2026-09-30"})
    assert [r["key"] for r in results] == ["nha_hang_sep"]
