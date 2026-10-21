"""API Receipt OCR (Phase 13): upload → extract (AI giả) → draft / failed → confirm / retry."""

import base64
import io
import json
import logging
import shutil
import uuid
from datetime import date

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.ai import openai_client
from app.core.config import BACKEND_DIR
from app.models import Receipt, Transaction
from app.services import receipt_storage

URL = "/api/v1/receipts"
TODAY = "2026-10-22"
JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"


def jpeg_bytes(size: int = 2048, seed: bytes = b"") -> bytes:
    body = seed + b"\x00" * max(0, size - len(JPEG_HEADER) - len(seed))
    return JPEG_HEADER + body


def heic_bytes() -> bytes:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 120, 200)).save(buffer, format="HEIF", quality=60)
    return buffer.getvalue()


def vision_json(**overrides) -> str:
    data = {
        "merchant": "Co.opmart",
        "date": "2026-10-05",
        "total": 352000,
        "currency": "VND",
        "items": [
            {"name": "Gạo ST25 5kg", "qty": 1, "amount": 185000},
            {"name": "Sữa tươi 1L", "qty": 2, "amount": 64000},
            {"name": "Rau cải", "qty": 2, "amount": 103000},
        ],
        "confidence": 0.93,
        "unreadable_reason": None,
        "category_slug": "food",
        "spending_type": "essential",
        "classification_reason": "Siêu thị bán thực phẩm",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


BLURRY = {
    "merchant": None,
    "date": None,
    "total": None,
    "items": [],
    "confidence": 0.42,
    "unreadable_reason": "blurry",
    "category_slug": "other",
    "spending_type": "non_essential",
    "classification_reason": "Không đọc được",
}


@pytest.fixture
def upload_dir(monkeypatch):
    root = (BACKEND_DIR / "uploads" / "_pytest" / uuid.uuid4().hex).resolve()
    monkeypatch.setattr(receipt_storage, "upload_root", lambda: root)
    yield root
    shutil.rmtree(root, ignore_errors=True)
    parent = root.parent
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def stored_files(root) -> list:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def upload(client, content: bytes, filename="receipt.jpg", content_type="image/jpeg", **params):
    return client.post(
        URL,
        params={"today": TODAY, **params},
        files={"file": (filename, content, content_type)},
    )


def transaction_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Transaction))


def receipt_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Receipt))


# ---------- upload ----------


def test_case_1_and_4_upload_extracts_draft(client, db, fake_ai, upload_dir):
    calls, responses = fake_ai
    responses.append(vision_json())
    before = transaction_count(db)

    resp = upload(client, jpeg_bytes(1_000_000))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    receipt = body["receipt"]
    assert body["status"] == receipt["status"] == "extracted"
    assert receipt["mime_type"] == "image/jpeg"
    assert receipt["original_filename"] == "receipt.jpg"
    assert receipt["file_size_bytes"] == 1_000_000
    assert receipt["model"] == openai_client.model_smart()
    assert receipt["error_code"] is None
    assert receipt["transaction_id"] is None

    files = stored_files(upload_dir)
    assert len(files) == 1
    today = date.today()
    expected = upload_dir / "receipts" / f"{today:%Y}" / f"{today:%m}" / f"{receipt['id']}.jpg"
    assert files[0] == expected
    row = db.get(Receipt, uuid.UUID(receipt["id"]))
    assert row.file_path == f"receipts/{today:%Y}/{today:%m}/{receipt['id']}.jpg"
    assert row.status == "extracted"

    draft = body["transaction_draft"]
    assert draft["amount"] == 352000
    assert draft["occurred_on"] == "2026-10-05"
    assert draft["direction"] == "expense"
    assert "Co.opmart" in draft["note"]
    assert draft["category_slug"] == "food"
    assert draft["spending_type"] == "essential"
    assert body["manual_prefill"] is None
    assert body["extraction"]["total"] == 352000
    assert len(body["extraction"]["items"]) == 3
    assert body["warnings"] == []
    assert body["duplicate_of"] is None
    assert body["transaction"] is None
    assert transaction_count(db) == before  # AI chỉ tạo draft

    # Một lời gọi vision: model smart, ảnh dạng data URL, không gửi lịch sử giao dịch.
    assert len(calls) == 1
    assert calls[0]["model"] == openai_client.model_smart()
    assert calls[0]["schema_name"] == "ReceiptVisionOutput"
    system, user = calls[0]["messages"]
    assert "| food |" in system["content"]
    image_part = next(p for p in user["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert base64.b64decode(image_part["image_url"]["url"].split(",", 1)[1]).startswith(JPEG_HEADER)


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("receipt.pdf", b"%PDF-1.7\n%fake", "application/pdf"),
        ("notes.txt", b"hello", "text/plain"),
        ("receipt.jpg", b"%PDF-1.7\n%fake", "image/jpeg"),
    ],
)
def test_case_2_rejects_non_images(
    client, db, fake_ai, upload_dir, filename, content, content_type
):
    calls, _ = fake_ai
    before = receipt_count(db)
    resp = upload(client, content, filename, content_type)
    assert resp.status_code == 415
    assert resp.json()["code"] == "unsupported_file_type"
    assert receipt_count(db) == before
    assert stored_files(upload_dir) == []
    assert calls == []


def test_case_3_rejects_files_over_10mb(client, db, fake_ai, upload_dir):
    calls, _ = fake_ai
    before = receipt_count(db)
    resp = upload(client, jpeg_bytes(10_500_000))
    assert resp.status_code == 413
    assert resp.json()["code"] == "file_too_large"
    assert "10MB" in resp.json()["detail"]
    assert receipt_count(db) == before
    assert stored_files(upload_dir) == []
    assert calls == []


def test_case_5_low_confidence_marks_failed_with_manual_prefill(client, db, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json(**BLURRY))
    before = transaction_count(db)

    resp = upload(client, jpeg_bytes())

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "unreadable"
    assert "blurry" in body["receipt"]["error_message"]
    assert body["transaction_draft"] is None
    prefill = body["manual_prefill"]
    assert prefill["amount"] is None
    assert prefill["occurred_on"] == TODAY
    assert prefill["direction"] == "expense"
    assert prefill["category_slug"] == "other"
    assert body["extraction"]["unreadable_reason"] == "blurry"
    assert transaction_count(db) == before
    assert len(stored_files(upload_dir)) == 1


def test_low_confidence_with_total_prefills_amount(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json(confidence=0.5))
    body = upload(client, jpeg_bytes()).json()
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "low_confidence"
    assert body["manual_prefill"]["amount"] == 352000
    assert body["manual_prefill"]["category_slug"] == "food"
    assert body["manual_prefill"]["spending_type"] == "essential"


def test_foreign_currency_needs_manual_entry(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json(currency="USD", total=25))
    body = upload(client, jpeg_bytes()).json()
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "unsupported_currency"
    assert body["manual_prefill"]["amount"] is None


def test_ai_not_configured_marks_failed(client, db, monkeypatch, upload_dir):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    resp = upload(client, jpeg_bytes())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "AI_NOT_CONFIGURED"
    assert body["extraction"] is None
    assert body["manual_prefill"] == {
        "direction": "expense",
        "amount": None,
        "occurred_on": TODAY,
        "note": "Hoá đơn",
        "category_id": None,
        "category_slug": None,
        "spending_type": None,
    }
    assert len(stored_files(upload_dir)) == 1


def test_invalid_ai_output_marks_failed(client, fake_ai, upload_dir):
    calls, responses = fake_ai
    responses.extend([vision_json(category_slug="khong_co"), vision_json(category_slug="salary")])
    body = upload(client, jpeg_bytes()).json()
    assert len(calls) == 2  # model được sửa 1 lần
    # messages là cùng một list được nối thêm: [system, user, output 1, góp ý 1, …]
    assert "khong_co" in calls[1]["messages"][3]["content"]
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "AI_INVALID_OUTPUT"


def test_invalid_output_fixed_on_second_attempt(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.extend([vision_json(total=0), vision_json()])
    body = upload(client, jpeg_bytes()).json()
    assert body["status"] == "extracted"
    assert body["transaction_draft"]["amount"] == 352000


def test_heic_upload_sent_as_jpeg_and_previewable(client, fake_ai, upload_dir):
    calls, responses = fake_ai
    responses.append(vision_json())
    resp = upload(client, heic_bytes(), "IMG_0001.HEIC", "application/octet-stream")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["receipt"]["mime_type"] == "image/heic"
    assert stored_files(upload_dir)[0].suffix == ".heic"
    image_part = next(p for p in calls[0]["messages"][1]["content"] if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")

    preview = client.get(f"{URL}/{body['receipt']['id']}/file")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert preview.content.startswith(b"\xff\xd8\xff")


def test_file_endpoint_serves_original(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json())
    content = jpeg_bytes(seed=b"abc")
    receipt_id = upload(client, content).json()["receipt"]["id"]
    resp = client.get(f"{URL}/{receipt_id}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == content
    assert client.get(f"{URL}/{uuid.uuid4()}/file").status_code == 404


def test_file_missing_on_disk(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json())
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    for path in stored_files(upload_dir):
        path.unlink()
    resp = client.get(f"{URL}/{receipt_id}/file")
    assert resp.status_code == 404
    assert resp.json()["code"] == "receipt_file_missing"


def test_duplicate_upload_warns(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.extend([vision_json(), vision_json()])
    content = jpeg_bytes(seed=b"same-image")
    first = upload(client, content).json()
    second = upload(client, content).json()
    assert first["duplicate_of"] is None
    assert second["duplicate_of"] == first["receipt"]["id"]
    assert second["receipt"]["id"] != first["receipt"]["id"]
    assert any("đã được tải lên" in w for w in second["warnings"])


def test_image_bytes_not_logged(client, fake_ai, upload_dir, caplog):
    _, responses = fake_ai
    responses.append(vision_json())
    content = jpeg_bytes(seed=b"secret-pixels")
    encoded = base64.b64encode(content).decode()
    with caplog.at_level(logging.DEBUG):
        upload(client, content)
    assert encoded[:40] not in caplog.text
    assert "secret-pixels" not in caplog.text
    assert "receipt_vision" in caplog.text


# ---------- confirm ----------


def test_case_6_confirm_creates_receipt_transaction(client, db, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.append(vision_json())
    detail = upload(client, jpeg_bytes()).json()
    receipt_id = detail["receipt"]["id"]

    resp = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 352000,
            "occurred_on": "2026-10-05",
            "category_id": categories["food"]["id"],
            "spending_type": "essential",
            "note": "Co.opmart - hoá đơn",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    tx = body["transaction"]
    assert tx["source"] == "receipt"
    assert tx["receipt_id"] == receipt_id
    assert tx["amount"] == 352000
    assert tx["direction"] == "expense"
    assert tx["category"]["slug"] == "food"
    assert tx["raw_input"] == "Hoá đơn Co.opmart (receipt.jpg)"
    assert tx["ai_suggestion"]["amount"] == 352000
    assert tx["ai_suggestion"]["model"] == openai_client.model_smart()
    assert tx["ai_suggestion"]["receipt_extraction"]["merchant"] == "Co.opmart"
    assert body["receipt"]["status"] == "confirmed"
    assert body["receipt"]["transaction_id"] == tx["id"]
    assert body["learned_preference"] is None
    assert body["pyf_proposal"] is None

    assert client.get(f"/api/v1/transactions/{tx['id']}").json()["receipt_id"] == receipt_id
    after = client.get(f"{URL}/{receipt_id}").json()
    assert after["status"] == "confirmed"
    assert after["transaction"]["id"] == tx["id"]
    assert after["manual_prefill"] is None

    again = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 352000,
            "occurred_on": "2026-10-05",
            "category_id": categories["food"]["id"],
        },
    )
    assert again.status_code == 409
    assert again.json()["code"] == "receipt_already_confirmed"


def test_confirm_edited_values_and_learns_merchant(client, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.extend([vision_json(), vision_json()])
    receipt_id = upload(client, jpeg_bytes(seed=b"1")).json()["receipt"]["id"]

    resp = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 350000,
            "occurred_on": "2026-10-06",
            "category_id": categories["shopping"]["id"],
            "spending_type": "non_essential",
            "note": "Đồ dùng nhà",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["transaction"]["amount"] == 350000
    assert body["transaction"]["note"] == "Đồ dùng nhà"
    learned = body["learned_preference"]
    assert learned is not None
    assert learned["category"]["slug"] == "shopping"
    assert learned["spending_type"] == "non_essential"

    # Hoá đơn sau của cùng cửa hàng: phân loại theo sở thích đã học (không theo model).
    second = upload(client, jpeg_bytes(seed=b"2")).json()
    draft = second["transaction_draft"]
    assert draft["category_slug"] == "shopping"
    assert draft["spending_type"] == "non_essential"
    assert draft["matched_preference_id"] == learned["id"]
    assert "sở thích" in draft["reason"]


def test_confirm_failed_receipt_with_manual_values(client, db, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.append(vision_json(**BLURRY))
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    resp = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 120000,
            "occurred_on": "2026-10-20",
            "category_id": categories["food"]["id"],
            "note": "Tạp hoá",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["transaction"]["source"] == "receipt"
    assert body["transaction"]["spending_type"] == "essential"
    assert body["transaction"]["ai_suggestion"]["receipt_extraction"]["total"] is None
    assert "category_id" not in body["transaction"]["ai_suggestion"]
    assert body["learned_preference"] is None
    assert body["receipt"]["status"] == "confirmed"
    assert body["receipt"]["error_code"] is None


def test_confirm_rejects_wrong_category_kind(client, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.append(vision_json())
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    resp = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 352000,
            "occurred_on": "2026-10-05",
            "category_id": categories["salary"]["id"],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "category_kind_mismatch"
    assert client.get(f"{URL}/{receipt_id}").json()["status"] == "extracted"


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 0, "occurred_on": "2026-10-05"},
        {"amount": 1.5, "occurred_on": "2026-10-05"},
        {"amount": 1000, "occurred_on": "2026-10-05", "source": "manual"},
    ],
)
def test_confirm_validates_body(client, fake_ai, upload_dir, categories, payload):
    _, responses = fake_ai
    responses.append(vision_json())
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    resp = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={"category_id": categories["food"]["id"], **payload},
    )
    assert resp.status_code == 422


def test_confirm_unknown_receipt(client, categories):
    resp = client.post(
        f"{URL}/{uuid.uuid4()}/confirm",
        json={"amount": 1000, "occurred_on": "2026-10-05", "category_id": categories["food"]["id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "receipt_not_found"


def test_deleting_transaction_keeps_receipt(client, db, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.append(vision_json())
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    tx = client.post(
        f"{URL}/{receipt_id}/confirm",
        json={
            "amount": 352000,
            "occurred_on": "2026-10-05",
            "category_id": categories["food"]["id"],
        },
    ).json()["transaction"]
    assert client.delete(f"/api/v1/transactions/{tx['id']}").status_code == 204
    db.expire_all()
    detail = client.get(f"{URL}/{receipt_id}").json()
    assert detail["status"] == "confirmed"
    assert detail["receipt"]["transaction_id"] is None
    assert detail["transaction"] is None


# ---------- retry ----------


def test_case_7_retry_failed_receipt(client, db, fake_ai, upload_dir):
    calls, responses = fake_ai
    responses.extend([vision_json(**BLURRY), vision_json()])
    first = upload(client, jpeg_bytes()).json()
    receipt_id = first["receipt"]["id"]
    assert first["status"] == "failed"
    files_before = stored_files(upload_dir)

    resp = client.post(f"{URL}/{receipt_id}/retry", params={"today": TODAY})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "extracted"
    assert body["receipt"]["id"] == receipt_id
    assert body["receipt"]["error_code"] is None
    assert body["transaction_draft"]["amount"] == 352000
    assert body["manual_prefill"] is None
    assert stored_files(upload_dir) == files_before
    assert len(calls) == 2


def test_retry_after_ai_not_configured(client, monkeypatch, fake_ai, upload_dir):
    _, responses = fake_ai
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: True)
    responses.append(vision_json())
    body = client.post(f"{URL}/{receipt_id}/retry").json()
    assert body["status"] == "extracted"


def test_retry_rejected_for_extracted_or_confirmed(client, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.append(vision_json())
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    resp = client.post(f"{URL}/{receipt_id}/retry")
    assert resp.status_code == 409
    assert resp.json()["code"] == "receipt_not_retryable"
    assert client.post(f"{URL}/{uuid.uuid4()}/retry").status_code == 404


def test_retry_when_file_missing(client, fake_ai, upload_dir):
    _, responses = fake_ai
    responses.append(vision_json(**BLURRY))
    receipt_id = upload(client, jpeg_bytes()).json()["receipt"]["id"]
    for path in stored_files(upload_dir):
        path.unlink()
    body = client.post(f"{URL}/{receipt_id}/retry").json()
    assert body["status"] == "failed"
    assert body["receipt"]["error_code"] == "file_missing"


# ---------- list / detail ----------


def test_list_and_detail(client, fake_ai, upload_dir, categories):
    _, responses = fake_ai
    responses.extend(
        [vision_json(), vision_json(**BLURRY), vision_json(merchant="Cà phê Mây", total=119000)]
    )
    first = upload(client, jpeg_bytes(seed=b"a"), "a.jpg").json()
    second = upload(client, jpeg_bytes(seed=b"b"), "b.png", "image/png").json()
    third = upload(client, jpeg_bytes(seed=b"c"), "c.jpg").json()
    assert second["status"] == "failed"
    # b.png có nội dung JPEG → lưu theo nội dung thật.
    assert second["receipt"]["mime_type"] == "image/jpeg"
    client.post(
        f"{URL}/{first['receipt']['id']}/confirm",
        json={
            "amount": 352000,
            "occurred_on": "2026-10-05",
            "category_id": categories["food"]["id"],
        },
    )

    items = client.get(URL).json()["items"]
    ids = [i["id"] for i in items]
    assert ids[:3] == [third["receipt"]["id"], second["receipt"]["id"], first["receipt"]["id"]]
    top = items[0]
    assert top["merchant"] == "Cà phê Mây"
    assert top["total"] == 119000
    assert top["receipt_date"] == "2026-10-05"
    assert top["status"] == "extracted"
    assert items[2]["status"] == "confirmed"
    assert items[2]["transaction_id"] is not None
    assert items[2]["transaction_occurred_on"] == "2026-10-05"
    assert top["transaction_occurred_on"] is None
    assert items[1]["error_code"] == "unreadable"

    failed = client.get(URL, params={"status": "failed"}).json()["items"]
    assert [i["id"] for i in failed] == [second["receipt"]["id"]]
    assert len(client.get(URL, params={"limit": 2}).json()["items"]) == 2
    assert client.get(URL, params={"status": "nope"}).status_code == 422
    assert client.get(URL, params={"limit": 0}).status_code == 422

    detail = client.get(f"{URL}/{third['receipt']['id']}", params={"today": TODAY}).json()
    assert detail["transaction_draft"]["amount"] == 119000
    assert detail["extraction"]["merchant"] == "Cà phê Mây"
    assert client.get(f"{URL}/{uuid.uuid4()}").status_code == 404
