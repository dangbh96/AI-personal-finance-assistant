"""Semantic search giao dịch (Phase 15 § 6) — embedding giả deterministic, không cần key."""

import uuid
from datetime import date

import openai
import pytest
from sqlalchemy import func, select

from app.agents.tools import finance_tools
from app.agents.tools.registry import CoachToolContext
from app.ai import embeddings, openai_client
from app.models import TransactionEmbedding
from app.repositories import embedding_repository
from app.schemas.coach import SearchTransactionsOutput
from app.schemas.transaction import TransactionCreate
from app.services import coach_evidence, embedding_service, transaction_service

TX_URL = "/api/v1/transactions"
URL = "/api/v1/search/transactions"
TODAY = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)


@pytest.fixture
def add(client, categories):
    def _add(note: str | None, amount: int, occurred_on: str, slug: str = "food") -> dict:
        category = categories[slug]
        resp = client.post(
            TX_URL,
            json={
                "direction": category["kind"],
                "amount": amount,
                "occurred_on": occurred_on,
                "category_id": category["id"],
                "note": note,
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _add


@pytest.fixture
def dataset(add):
    """Tháng 9–10/2026: ăn ngoài, đi lại, cà phê, mua sắm, lương."""
    rows = {
        "nha_hang": add("Nhà hàng Hải Sản Biển Đông", 650_000, "2026-10-05"),
        "quan_nuong": add("Quán nướng Gò Vấp", 420_000, "2026-10-08"),
        "bun_cha": add("Bún chả Hàng Mành", 45_000, "2026-10-12"),
        "nha_hang_sep": add("Nhà hàng chay Hương Sen", 380_000, "2026-09-18"),
        "cho": add("Đi chợ mua rau", 120_000, "2026-10-03"),
        "grab": add("Grab về nhà", 85_000, "2026-10-06", "transport"),
        "xang": add("Đổ xăng xe máy", 70_000, "2026-10-09", "transport"),
        "bus": add("Vé xe bus tháng", 200_000, "2026-10-01", "transport"),
        "highlands": add("Cà phê Highlands", 59_000, "2026-10-10"),
        "cafe": add("Cafe sữa đá cóc", 20_000, "2026-10-11"),
        "giay": add("Mua giày chạy bộ", 1_500_000, "2026-10-14", "shopping"),
        "luong": add("Lương tháng 10", 25_000_000, "2026-10-01", "salary"),
    }
    return rows


def _ids(body: dict) -> list[str]:
    return [r["transaction_id"] for r in body["results"]]


def _search(client, q: str, **params) -> dict:
    resp = client.get(URL, params={"q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- embedding khi tạo / sửa / xoá (test case 1, 3) -------------------------------------------


def test_create_embeds_transaction(client, db, add):
    tx = add("Bún chả Hàng Mành", 45_000, "2026-10-12")
    row = embedding_repository.get(db, uuid.UUID(tx["id"]))
    assert row is not None
    assert row.content == "Bún chả Hàng Mành. Danh mục: Ăn uống. Khoản <100k. Loại: thiết yếu."
    assert row.model == openai_client.embedding_model()
    assert len(row.embedding) == 1536


def test_create_succeeds_when_embedding_fails(client, db, add, monkeypatch):
    """Test case 1: lỗi embedding không chặn lưu giao dịch."""

    def boom(**_):
        raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]

    monkeypatch.setattr(openai_client, "_embed_raw", boom)
    tx = add("Bún chả Hàng Mành", 45_000, "2026-10-12")
    assert client.get(f"{TX_URL}/{tx['id']}").status_code == 200
    assert embedding_repository.get(db, uuid.UUID(tx["id"])) is None


def test_create_without_ai_key_still_201(client, db, add, monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    tx = add("Phở bò", 50_000, "2026-10-12")
    assert embedding_repository.get(db, uuid.UUID(tx["id"])) is None


def test_update_note_reembeds_and_same_content_skips(client, db, add, monkeypatch):
    """Test case 3: sửa ghi chú → `content` và `embedded_at` đổi."""
    tx = add("Phở bò", 50_000, "2026-10-12")
    tid = uuid.UUID(tx["id"])
    before = embedding_repository.get(db, tid)
    old_content, old_at = before.content, before.embedded_at

    resp = client.patch(f"{TX_URL}/{tx['id']}", json={"note": "Bún chả Hàng Mành"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "Bún chả Hàng Mành"
    db.expire_all()
    after = embedding_repository.get(db, tid)
    assert after.content.startswith("Bún chả Hàng Mành.") and after.content != old_content
    assert after.embedded_at > old_at

    # Đổi số tiền trong cùng khoảng → nội dung không đổi → không gọi lại embedding.
    calls = []
    real = openai_client._embed_raw

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(openai_client, "_embed_raw", spy)
    assert client.patch(f"{TX_URL}/{tx['id']}", json={"amount": 60_000}).status_code == 200
    assert calls == []

    # Đổi danh mục → nội dung đổi.
    categories = {c["slug"]: c for c in client.get("/api/v1/categories").json()}
    client.patch(f"{TX_URL}/{tx['id']}", json={"category_id": categories["shopping"]["id"]})
    db.expire_all()
    assert "Danh mục: Mua sắm." in embedding_repository.get(db, tid).content


def test_delete_transaction_cascades_embedding(client, db, add):
    tx = add("Phở bò", 50_000, "2026-10-12")
    assert client.delete(f"{TX_URL}/{tx['id']}").status_code == 204
    db.expire_all()
    assert embedding_repository.get(db, uuid.UUID(tx["id"])) is None


# --- backfill / reindex (test case 2) ---------------------------------------------------------


def _create_without_embedding(db, categories, n: int) -> list[uuid.UUID]:
    ids = []
    for i in range(n):
        t = transaction_service.create_transaction(
            db,
            TransactionCreate(
                direction="expense",
                amount=10_000 * (i + 1),
                occurred_on=date(2026, 10, 1 + i),
                category_id=categories["food"]["id"],
                note=f"Bữa trưa {i}",
            ),
        )
        ids.append(t.id)
    return ids


def test_backfill_creates_missing(db, categories):
    """Test case 2: 12 giao dịch thiếu embedding → tạo đủ 12 dòng; chạy lại không gọi AI."""
    _create_without_embedding(db, categories, 12)
    assert embedding_repository.count_missing(db) == 12
    progress = []
    report = embedding_service.backfill(
        db, embeddings.embed_documents, batch_size=5, on_batch=lambda s, p: progress.append(p)
    )
    assert (report.scanned, report.processed, report.remaining_missing) == (12, 12, 0)
    assert progress == [5, 10, 12]
    assert db.scalar(select(func.count()).select_from(TransactionEmbedding)) == 12

    again = embedding_service.backfill(db, embeddings.embed_documents, batch_size=50)
    assert (again.processed, again.unchanged) == (0, 12)


def test_backfill_limit_and_force(db, categories):
    _create_without_embedding(db, categories, 6)
    report = embedding_service.backfill(db, embeddings.embed_documents, batch_size=4, limit=3)
    assert report.processed == 3 and report.remaining_missing == 3
    forced = embedding_service.backfill(db, embeddings.embed_documents, force=True)
    assert forced.processed == 6 and forced.remaining_missing == 0


def test_reindex_endpoint(client, db, categories):
    ids = _create_without_embedding(db, categories, 3)
    resp = client.post(f"{URL}/reindex", json={})
    assert resp.status_code == 200
    assert resp.json() == {"processed_count": 3, "unchanged_count": 0, "remaining_count": 0}
    again = client.post(f"{URL}/reindex").json()
    assert again["processed_count"] == 0 and again["unchanged_count"] == 3
    one = client.post(f"{URL}/reindex", json={"transaction_ids": [str(ids[0])]}).json()
    assert one["processed_count"] == 1  # chỉ định id → embed lại
    assert client.post(f"{URL}/reindex", json={"limit": 0}).status_code == 422


# --- tìm kiếm (test case 4–8) -----------------------------------------------------------------


def test_search_eating_out_semantic(client, dataset):
    """Test case 4: "ăn ngoài" → nhà hàng, quán nướng, bún chả trong top 10."""
    body = _search(client, "ăn ngoài")
    ids = _ids(body)[:10]
    for key in ("nha_hang", "quan_nuong", "bun_cha", "nha_hang_sep"):
        assert dataset[key]["id"] in ids
    for key in ("grab", "xang", "luong", "giay"):
        assert dataset[key]["id"] not in ids
    first = body["results"][0]
    assert first["match_reason"] == "semantic" and first["semantic_score"] > 0.2
    assert body["query"] == "ăn ngoài" and body["missing_embedding_count"] == 0


def test_search_travel(client, dataset):
    """Test case 5: "đi lại" → grab, xăng, vé xe bus."""
    ids = _ids(_search(client, "đi lại"))[:10]
    for key in ("grab", "xang", "bus"):
        assert dataset[key]["id"] in ids
    assert dataset["bun_cha"]["id"] not in ids


def test_search_date_filter(client, dataset):
    """Test case 6: lọc tháng 9 → không trả dòng ngoài tháng 9."""
    body = _search(client, "ăn ngoài", **{"from": "2026-09-01", "to": "2026-09-30"})
    assert _ids(body) == [dataset["nha_hang_sep"]["id"]]
    assert all("2026-09-01" <= r["occurred_on"] <= "2026-09-30" for r in body["results"])
    assert body["from_date"] == "2026-09-01" and body["total_amount"] == 380_000


def test_search_keyword_boost_highlands(client, dataset):
    """Test case 7: từ khoá chính xác "Highlands" được boost lên top 3."""
    body = _search(client, "Highlands")
    top3 = _ids(body)[:3]
    assert dataset["highlands"]["id"] == top3[0]
    first = body["results"][0]
    assert first["keyword_boost"] == 1.0 and first["match_reason"] == "hybrid"


def test_search_totals_and_limit(client, dataset):
    body = _search(client, "đi lại", limit=2)
    assert body["result_count"] == 2 == len(body["results"])
    expense = sum(r["amount"] for r in body["results"] if r["direction"] == "expense")
    assert body["expense_total"] == body["total_amount"] == expense
    assert body["net"] == body["income_total"] - body["expense_total"]
    salary = _search(client, "lương")
    assert salary["results"][0]["direction"] == "income"
    assert salary["income_total"] == 25_000_000


def test_search_keyword_only_when_not_embedded(client, db, categories, add, monkeypatch):
    def boom(**_):
        raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]

    real = openai_client._embed_raw
    monkeypatch.setattr(openai_client, "_embed_raw", boom)
    tx = add("Highlands Coffee Landmark", 75_000, "2026-10-15")
    monkeypatch.setattr(openai_client, "_embed_raw", real)
    body = _search(client, "highlands")
    assert body["missing_embedding_count"] == 1
    hit = next(r for r in body["results"] if r["transaction_id"] == tx["id"])
    assert hit["match_reason"] == "keyword" and hit["semantic_score"] is None
    assert hit["score"] == 0.25


def test_search_no_ai_key_503(client, dataset, monkeypatch):
    """Test case 8: thiếu key → 503, app không crash."""
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    resp = client.get(URL, params={"q": "ăn ngoài"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "AI_NOT_CONFIGURED"
    assert client.get(TX_URL).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "x" * 201},
        {"q": "a" * 5000},
        {"q": "ăn", "limit": 0},
        {"q": "ăn", "limit": 51},
        {"q": "ăn", "from": "2026-10-31", "to": "2026-10-01"},
        {},
    ],
)
def test_search_validation(client, params):
    resp = client.get(URL, params=params)
    assert resp.status_code == 422


def test_search_blank_query_and_like_wildcards(client, dataset):
    assert client.get(URL, params={"q": "   "}).json()["code"] == "empty_query"
    # `%` / `_` được escape — không khớp mọi dòng.
    body = _search(client, "%_%")
    assert all(r["keyword_boost"] == 0 for r in body["results"])


def test_search_empty_db(client):
    body = _search(client, "ăn ngoài")
    assert body["results"] == [] and body["total_amount"] == 0


# --- Coach tool search_transactions -----------------------------------------------------------


def test_coach_tool_search_transactions(db, dataset):
    ctx = CoachToolContext(db=db, today=TODAY, embedder=embeddings.embed_queries)
    tool = finance_tools.search_transactions_tool(ctx)
    ctx.recorder.begin("c1", "search_transactions", {"query": "ăn ngoài"})
    raw = tool.invoke(
        {"query": "ăn ngoài", "from_date": "2026-10-01", "to_date": "2026-10-31", "limit": 5}
    )
    ctx.recorder.finish("c1", 3, None)
    output = ctx.recorder.ordered()[0].output
    assert isinstance(output, SearchTransactionsOutput)
    notes = [i.note for i in output.items]
    assert {"Nhà hàng Hải Sản Biển Đông", "Quán nướng Gò Vấp", "Bún chả Hàng Mành"} <= set(notes)
    assert "Nhà hàng chay Hương Sen" not in notes  # tháng 9
    assert output.expense_total == sum(i.amount for i in output.items)
    assert '"expense_total"' in raw

    rows = coach_evidence.evidence_rows("search_transactions", output)
    assert any(r.amount == 650_000 and r.label == "“Nhà hàng Hải Sản Biển Đông”" for r in rows)
    assert rows[-1].metric == "Tổng chi" and rows[-1].amount == output.expense_total
    summary, count = coach_evidence.summarize_result(output)
    assert count == len(output.items) and "ăn ngoài" in summary


def test_coach_tool_without_embedder_errors(db):
    ctx = CoachToolContext(db=db, today=TODAY)
    tool = finance_tools.search_transactions_tool(ctx)
    with pytest.raises(Exception, match="chưa sẵn sàng"):
        tool.invoke({"query": "ăn ngoài"})
