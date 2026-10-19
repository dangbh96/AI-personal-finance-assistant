"""Golden test classification learning (Phase 3) — gọi OpenAI thật: `pytest -m ai -s`.

Chạy qua API trên DB test (rollback sau test). Các bước theo phase-03 § 6:
before → correction → after → explicit → similar brand → không liên quan → cafe → income →
irregular → xoá preference.

Ngưỡng: case exact-match (đi shortcut / hậu kiểm theo preference) đúng 100%; case do model
quyết định đúng ≥ 85%; không case nào dùng preference đã xoá.
"""

import sys

import pytest

from app.ai import openai_client

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

TODAY = "2026-10-07"
TX_URL = "/api/v1/transactions"
PREF_URL = "/api/v1/classification-preferences"
MODEL_THRESHOLD = 0.85


def _report(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


class Golden:
    def __init__(self, client):
        self.client = client
        self.results: list[tuple[str, str, bool, str]] = []  # (bước, loại, đạt, chi tiết)

    def parse(self, text: str) -> dict:
        resp = self.client.post(f"{TX_URL}/parse", json={"text": text, "today": TODAY})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        _report(f"\n{text!r} → model={body['model']} {body['drafts']}")
        return body

    def save(self, parsed: dict, category_id: str, spending_type: str | None) -> dict:
        draft = parsed["drafts"][0]
        resp = self.client.post(
            TX_URL,
            json={
                "direction": draft["direction"],
                "amount": draft["amount"],
                "occurred_on": draft["occurred_on"],
                "category_id": category_id,
                "spending_type": spending_type,
                "note": draft["note"],
                "source": "nl",
                "raw_input": parsed["raw_input"],
                "ai_suggestion": {**draft, "model": parsed["model"]},
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def explicit(self, text: str) -> dict:
        resp = self.client.post(f"{PREF_URL}/parse", json={"text": text})
        assert resp.status_code == 200, resp.text
        draft = resp.json()
        _report(f"\n{text!r} → {draft}")
        return draft

    def confirm(self, draft: dict) -> dict:
        resp = self.client.post(
            PREF_URL,
            json={
                k: draft[k] for k in ("pattern", "category_slug", "spending_type", "example_text")
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    def check(self, step: str, kind: str, ok: bool, detail: str) -> None:
        self.results.append((step, kind, ok, detail))


def test_classification_learning_golden(client):
    g = Golden(client)
    categories = {c["slug"]: c for c in client.get("/api/v1/categories").json()}

    # 1. Before preference
    before = g.parse("Mua giày MLB 1.8 triệu")
    d = before["drafts"][0]
    g.check(
        "1 before",
        "model",
        d["amount"] == 1_800_000
        and d["direction"] == "expense"
        and d["category_slug"] == "shopping",
        f"{d['amount']} {d['category_slug']}/{d['spending_type']}",
    )

    # 2. Correction → shopping + essential
    tx = g.save(before, categories["shopping"]["id"], "essential")
    learned = tx["learned_preference"]
    if learned is None:
        # Model đã đề xuất đúng shopping/essential → không có correction; tạo preference tường minh.
        _report("   (model đã đề xuất essential sẵn — tạo preference 'giày' tường minh)")
        learned = g.confirm(
            {
                "pattern": "giày",
                "category_slug": "shopping",
                "spending_type": "essential",
                "example_text": "Mua giày MLB 1.8 triệu",
            }
        )
    g.check(
        "2 correction",
        "exact",
        "giay" in learned["pattern"].split() and learned["spending_type"] == "essential",
        f"pattern={learned['pattern']} type={learned['spending_type']}",
    )

    # 3. After preference
    d = g.parse("Mua giày Nike 2tr")["drafts"][0]
    g.check(
        "3 after",
        "exact",
        d["category_slug"] == "shopping"
        and d["spending_type"] == "essential"
        and d["matched_preference_id"] is not None,
        f"{d['category_slug']}/{d['spending_type']} matched={d['matched_preference_id']}",
    )

    # 4. Explicit preference (chỉ parse, không lưu)
    draft = g.explicit("Tao coi giày là thiết yếu")
    g.check(
        "4 explicit",
        "model",
        draft["pattern"] == "giay" and draft["spending_type"] == "essential",
        f"pattern={draft['pattern']} {draft['category_slug']}/{draft['spending_type']}",
    )

    # 5. Similar brand
    d = g.parse("Đặt giày Adidas 1tr2")["drafts"][0]
    g.check(
        "5 similar brand",
        "exact",
        d["category_slug"] == "shopping"
        and d["spending_type"] == "essential"
        and d["amount"] == 1_200_000,
        f"{d['amount']} {d['category_slug']}/{d['spending_type']}",
    )

    # 6. Không liên quan
    d = g.parse("Mua áo 450k")["drafts"][0]
    g.check(
        "6 unrelated",
        "model",
        d["matched_preference_id"] is None and d["spending_type"] != "essential",
        f"{d['category_slug']}/{d['spending_type']} matched={d['matched_preference_id']}",
    )

    # 7. Food correction → food/non_essential; lần sau "cafe 2 lít"
    cafe = g.parse("Cafe với khách 200k")
    g.save(cafe, categories["food"]["id"], "non_essential")
    d = g.parse("cafe 2 lít")["drafts"][0]
    g.check(
        "7 cafe",
        "exact" if d["matched_preference_id"] else "model",
        d["category_slug"] == "food"
        and d["spending_type"] == "non_essential"
        and d["amount"] == 200_000,
        f"{d['amount']} {d['category_slug']}/{d['spending_type']} "
        f"matched={d['matched_preference_id']}",
    )

    # 8. Income không bị ảnh hưởng
    d = g.parse("Nhận lương 25 triệu")["drafts"][0]
    g.check(
        "8 income",
        "model",
        d["category_slug"] == "salary" and d["spending_type"] is None,
        f"{d['category_slug']}/{d['spending_type']}",
    )

    # 9. Irregular preference (explicit, xác nhận) → "sửa màn hình laptop 900k"
    laptop = g.explicit("Sửa laptop là bất thường")
    g.check(
        "9a explicit irregular",
        "model",
        laptop["spending_type"] == "irregular" and "laptop" in laptop["pattern"].split(),
        f"pattern={laptop['pattern']} {laptop['category_slug']}/{laptop['spending_type']}",
    )
    g.confirm(laptop)
    d = g.parse("sửa màn hình laptop 900k")["drafts"][0]
    g.check(
        "9b irregular after",
        "exact",
        d["spending_type"] == "irregular" and d["matched_preference_id"] is not None,
        f"{d['category_slug']}/{d['spending_type']} matched={d['matched_preference_id']}",
    )

    # 10. Xoá preference giày → không dùng nữa
    giay = next(p for p in client.get(PREF_URL).json()["items"] if "giay" in p["pattern"].split())
    assert client.delete(f"{PREF_URL}/{giay['id']}").status_code == 204
    d = g.parse("Mua giày Nike 2tr")["drafts"][0]
    g.check(
        "10 deleted",
        "exact",
        d["matched_preference_id"] != giay["id"] and d["matched_preference_id"] is None,
        f"{d['category_slug']}/{d['spending_type']} matched={d['matched_preference_id']}",
    )

    lines = [
        f"  [{'✓' if ok else '✗'}] {step:<22} ({kind}) {detail}"
        for step, kind, ok, detail in g.results
    ]
    exact = [ok for _, kind, ok, _ in g.results if kind == "exact"]
    model = [ok for _, kind, ok, _ in g.results if kind == "model"]
    exact_score = sum(exact) / len(exact)
    model_score = sum(model) / len(model)
    summary = (
        f"\nModel: {openai_client.model_fast()}\n"
        + "\n".join(lines)
        + f"\n  exact: {sum(exact)}/{len(exact)} = {exact_score:.0%} (ngưỡng 100%)"
        + f"\n  model: {sum(model)}/{len(model)} = {model_score:.0%} "
        f"(ngưỡng {MODEL_THRESHOLD:.0%})"
    )
    _report(summary)

    assert exact_score == 1.0, summary
    assert model_score >= MODEL_THRESHOLD, summary
