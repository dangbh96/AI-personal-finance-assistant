"""Phase 15: nội dung embed, khoảng tiền, chấm điểm từ khoá, client embeddings (không cần DB)."""

import openai
import pytest

from app.ai import embeddings, openai_client
from app.ai.openai_client import AIUnavailable, EmbeddingResult
from app.models import Category, Transaction
from app.services import embedding_service, search_service
from app.services.embedding_service import (
    amount_bucket,
    build_transaction_embedding_content,
    clean_note,
)
from tests.fake_embeddings import fake_vector


def _tx(note, amount=45_000, direction="expense", spending_type="essential", category="Ăn uống"):
    return Transaction(
        note=note,
        amount=amount,
        direction=direction,
        spending_type=spending_type if direction == "expense" else None,
        category=Category(name=category, kind=direction, slug="x"),
    )


@pytest.mark.parametrize(
    ("amount", "bucket"),
    [
        (1, "<100k"),
        (99_999, "<100k"),
        (100_000, "100k-500k"),
        (499_999, "100k-500k"),
        (500_000, "500k-2m"),
        (1_999_999, "500k-2m"),
        (2_000_000, "2m-10m"),
        (9_999_999, "2m-10m"),
        (10_000_000, ">10m"),
        (250_000_000, ">10m"),
    ],
)
def test_amount_bucket(amount, bucket):
    assert amount_bucket(amount) == bucket


def test_content_expense():
    content = build_transaction_embedding_content(_tx("Bún chả Hàng Mành"))
    assert content == "Bún chả Hàng Mành. Danh mục: Ăn uống. Khoản <100k. Loại: thiết yếu."


def test_content_income_and_no_note():
    income = _tx(None, amount=25_000_000, direction="income", category="Lương")
    assert build_transaction_embedding_content(income) == (
        "Danh mục: Lương. Khoản >10m. Loại: thu nhập."
    )
    other = _tx("  ", amount=600_000, spending_type="non_essential", category="Mua sắm")
    assert build_transaction_embedding_content(other) == (
        "Danh mục: Mua sắm. Khoản 500k-2m. Loại: không thiết yếu."
    )
    irregular = _tx("Sửa xe", amount=1_200_000, spending_type="irregular", category="Đi lại")
    assert build_transaction_embedding_content(irregular).endswith("Loại: bất thường.")


def test_clean_note_statement_style():
    # Sao kê: viết hoa, mã giao dịch / số tài khoản dài → bỏ, chữ thường.
    assert clean_note("THANH TOAN QR GRAB 0123456789 FT26290") == "Thanh toan qr grab"
    assert clean_note("Highlands Coffee - Q1") == "Highlands Coffee - Q1"
    assert clean_note("Mua 2 ly trà sữa") == "Mua 2 ly trà sữa"
    assert clean_note(None) == ""
    assert len(clean_note("a" * 1000)) == embedding_service.MAX_NOTE_CHARS


def test_keyword_boost_rules():
    boost = search_service.keyword_boost
    assert boost("Highlands", "Cà phê Highlands Q1", "Ăn uống") == 1.0
    assert boost("highland", "HIGHLANDS COFFEE", "Ăn uống") == 1.0  # tiền tố từ, không dấu
    assert boost("ăn uống", "Bún chả", "Ăn uống") == 0.5  # tên danh mục
    assert boost("grab xăng", "Đổ xăng xe máy", "Đi lại") == 0.25  # 1/2 từ khoá
    assert boost("ăn ngoài", "Bán đồ cũ", "Thu nhập khác") == 0.0  # "an" ≠ "ban"
    assert boost("cà phê", None, "Đi lại") == 0.0


def test_keyword_tokens_and_sql_terms():
    assert search_service.keyword_tokens("Ăn ngoài tháng này") == ["an", "ngoai"]
    assert search_service.sql_terms("  grab   xăng  ") == ["grab xăng", "grab", "xăng"]
    assert search_service.sql_terms("đi lại") == ["đi lại", "lại"]
    assert search_service.combine_score(0.8, 1.0) == 0.85
    assert search_service.combine_score(None, 0.5) == 0.125
    assert search_service.embedding_query_text("ăn ngoài") == "Chi tiêu ăn ngoài"
    assert search_service.embedding_query_text("Chi tiêu đi lại") == "Chi tiêu đi lại"


def test_create_embeddings_batches_and_keeps_order(monkeypatch):
    calls = []

    def fake(*, model, inputs, timeout):
        calls.append(len(inputs))
        return EmbeddingResult([fake_vector(t) for t in inputs], model, len(inputs))

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_embed_raw", fake)
    texts = [f"giao dịch {i}" for i in range(230)]
    result = openai_client.create_embeddings(texts, task="test")
    assert calls == [100, 100, 30]
    assert len(result.vectors) == 230 and result.prompt_tokens == 230
    assert result.vectors[5] == fake_vector("giao dịch 5")
    assert result.model == openai_client.embedding_model()
    assert embeddings.embed_documents(["a"]).model == result.model


def test_create_embeddings_errors(monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    with pytest.raises(AIUnavailable) as exc:
        openai_client.create_embeddings(["x"], task="test")
    assert exc.value.code == "AI_NOT_CONFIGURED"

    def boom(**_):
        raise openai.APIConnectionError(request=None)  # type: ignore[arg-type]

    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(openai_client, "_embed_raw", boom)
    with pytest.raises(AIUnavailable) as exc:
        embeddings.embed_queries(["x"])
    assert exc.value.code == "AI_UNAVAILABLE" and exc.value.status_code == 503

    monkeypatch.setattr(openai_client, "_embed_raw", lambda **_: EmbeddingResult([], "m", 0))
    with pytest.raises(AIUnavailable) as exc:
        openai_client.create_embeddings(["x"], task="test")
    assert exc.value.code == "AI_INVALID_OUTPUT"
    assert openai_client.create_embeddings([], task="test").vectors == []


def test_fake_vectors_cluster_synonyms():
    def sim(a, b):
        return sum(x * y for x, y in zip(fake_vector(a), fake_vector(b), strict=True))

    assert sim("ăn ngoài", "Nhà hàng Hải Sản") > sim("ăn ngoài", "Đổ xăng")
    assert sim("đi lại", "Grab về nhà") > sim("đi lại", "Bún chả")
