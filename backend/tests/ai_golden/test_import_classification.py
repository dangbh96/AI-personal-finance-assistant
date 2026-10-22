"""Golden test phân loại hàng loạt khi import sao kê (Phase 14) — OpenAI thật: `pytest -m ai -s`.

Chạy qua API trên DB test (rollback sau test) với fixture giả `vcb_statement.csv` (22 dòng hợp lệ,
21 nội dung khác nhau → 2 request ≤ 20 dòng). Ngưỡng:
- danh mục đúng ≥ 85% số dòng hợp lệ; lương (`credit 25.000.000`) phải là `salary`;
- loại chi tiêu đúng ≥ 75% trên các dòng chi có kỳ vọng;
- mọi dòng có đề xuất từ AI (không rơi về `other` vì lỗi), chiều tiền / số tiền giữ nguyên;
- dòng exact-match sở thích đã học không được gửi cho model.
"""

import json
import sys
from pathlib import Path

import pytest

from app.ai import openai_client

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

URL = "/api/v1/imports/preview"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "imports"
CATEGORY_THRESHOLD = 0.85
SPENDING_THRESHOLD = 0.75

# nội dung → (danh mục chấp nhận, loại chi tiêu kỳ vọng hoặc None = không chấm)
EXPECTED: dict[str, tuple[set[str], str | None]] = {
    "Lương tháng 08/2026 công ty ABC": ({"salary"}, None),
    "GRAB*TRIP 1234 HCM": ({"transport"}, "essential"),
    "Ăn trưa quán bún bò": ({"food"}, None),
    "THANH TOAN TIEN DIEN EVN THANG 8": ({"utilities"}, "essential"),
    "GRAB*TRIP 5678 HCM": ({"transport"}, "essential"),
    "BACH HOA XANH Q7": ({"food"}, "essential"),
    "HIGHLANDS COFFEE VINCOM": ({"food"}, "non_essential"),
    "SHOPEE PAY DON HANG 260906": ({"shopping"}, "non_essential"),
    "NETFLIX.COM": ({"entertainment"}, "non_essential"),
    "GRAB*TRIP 9012 HCM": ({"transport"}, "essential"),
    "CK tiền nhà tháng 9 cho chủ nhà": ({"housing"}, "essential"),
    "NHA THUOC LONG CHAU": ({"health"}, None),
    "VIETTEL CUOC INTERNET T9": ({"utilities"}, "essential"),
    "Thanh toán dự án thiết kế logo": ({"freelance"}, None),
    "CGV CINEMAS VINCOM": ({"entertainment"}, "non_essential"),
    "Sửa xe máy Honda": ({"transport"}, "irregular"),
    "TRA SUA PHUC LONG": ({"food"}, "non_essential"),
    "WINMART THAO DIEN": ({"food"}, "essential"),
    "Học phí tiếng Anh tháng 9": ({"education"}, None),
    "HOAN TIEN DON HANG LAZADA": ({"other_income"}, None),
    "BE CAR CHUYEN DI": ({"transport"}, None),
}


def _report(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


@pytest.fixture
def categories(client) -> dict[str, dict]:
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    return {c["slug"]: c for c in resp.json()}


@pytest.fixture
def requests_sent(monkeypatch):
    """Đếm lời gọi Chat Completions thật (bọc `_chat_json`, vẫn gọi OpenAI)."""
    sent: list[list[dict]] = []
    original = openai_client._chat_json

    def _counting(**kwargs):
        sent.append(json.loads(kwargs["messages"][1]["content"].split("\n", 1)[1]))
        return original(**kwargs)

    monkeypatch.setattr(openai_client, "_chat_json", _counting)
    return sent


def _upload(client, name: str) -> dict:
    content = (FIXTURES / name).read_bytes()
    resp = client.post(URL, files={"file": (name, content, "")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_import_batch_classification_golden(client, categories, requests_sent):
    by_id = {c["id"]: c for c in categories.values()}
    body = _upload(client, "vcb_statement.csv")
    assert body["batch"]["ai_error_code"] is None, body["warnings"]
    assert body["batch"]["model"] == openai_client.model_fast()
    valid = [r for r in body["rows"] if r["status"] == "valid"]
    assert len(valid) == 22
    assert sorted(len(batch) for batch in requests_sent) == [1, 20]

    category_ok = spending_checked = spending_ok = 0
    _report("\n  dòng | nội dung | danh mục | loại | conf | lý do")
    for row in valid:
        expected_slugs, expected_type = EXPECTED[row["note"]]
        slug = by_id[row["suggested_category_id"]]["slug"]
        assert row["suggestion_source"] == "ai", row
        assert by_id[row["suggested_category_id"]]["kind"] == row["direction"]
        hit = slug in expected_slugs
        category_ok += hit
        type_mark = ""
        if expected_type is not None:
            spending_checked += 1
            spending_ok += row["suggested_spending_type"] == expected_type
            type_mark = "✓" if row["suggested_spending_type"] == expected_type else "✗"
        mark = "✓" if hit else "✗"
        _report(
            f"  {mark} {row['row_index']:>3} | {row['note'][:34]:<34} | {slug:<13} | "
            f"{row['suggested_spending_type'] or '—':<13}{type_mark} | {row['confidence']:.2f} | "
            f"{row['reason']}"
        )

    salary = next(r for r in valid if r["amount"] == 25_000_000)
    assert by_id[salary["suggested_category_id"]]["slug"] == "salary"
    category_rate = category_ok / len(valid)
    spending_rate = spending_ok / spending_checked
    _report(
        f"\n  danh mục đúng {category_ok}/{len(valid)} ({category_rate:.0%}), "
        f"loại chi tiêu đúng {spending_ok}/{spending_checked} ({spending_rate:.0%}), "
        f"requests={len(requests_sent)}"
    )
    assert category_rate >= CATEGORY_THRESHOLD
    assert spending_rate >= SPENDING_THRESHOLD


def test_preference_rows_skip_model(client, categories, requests_sent):
    resp = client.post(
        "/api/v1/classification-preferences",
        json={"pattern": "grab", "category_slug": "transport", "spending_type": "essential"},
    )
    assert resp.status_code == 201, resp.text
    body = _upload(client, "techcombank_statement.csv")
    assert body["batch"]["ai_error_code"] is None, body["warnings"]
    grab = [r for r in body["rows"] if r["note"].startswith("GRAB")]
    assert len(grab) == 3
    assert all(r["suggestion_source"] == "preference" for r in grab)
    assert all(r["suggested_category_id"] == categories["transport"]["id"] for r in grab)
    sent_notes = [item["note"] for batch in requests_sent for item in batch]
    assert not any(note.startswith("GRAB") for note in sent_notes)
    # 22 dòng hợp lệ − 3 Grab = 19 dòng, 18 nội dung khác nhau → đúng 1 request.
    assert len(requests_sent) == 1
    assert len(requests_sent[0]) == 18
    _report(
        f"\n  preference={body['summary']['preference_count']} ai={body['summary']['ai_count']}"
    )
