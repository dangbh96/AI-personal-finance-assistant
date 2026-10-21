"""Lưu ảnh hoá đơn (Phase 13): validate mime / đuôi / kích thước / magic bytes, đường dẫn."""

import io
import uuid
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from app.core.errors import DomainError
from app.services import receipt_storage
from app.services.receipt_storage import FileTooLarge, UnsupportedFileType

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
HEIF = b"\x00\x00\x00\x18ftypmif1" + b"\x00" * 64


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (WEBP, "image/webp"),
        (HEIC, "image/heic"),
        (HEIF, "image/heif"),
        (b"%PDF-1.7\n" + b"\x00" * 64, None),
        (b"hello world", None),
        (b"\x00\x00\x00\x18ftypavif" + b"\x00" * 64, None),
    ],
)
def test_sniff_image_type(content, expected):
    assert receipt_storage.sniff_image_type(content) == expected


def test_validate_jpeg():
    image = receipt_storage.validate_image(JPEG, "image/jpeg", "receipt.JPG")
    assert image.mime_type == "image/jpeg"
    assert image.extension == ".jpg"
    assert image.size == len(JPEG)
    assert len(image.sha256) == 64
    assert image.original_filename == "receipt.JPG"


@pytest.mark.parametrize(
    ("content_type", "filename"),
    [
        ("application/pdf", "receipt.pdf"),
        ("text/plain", "receipt.txt"),
        ("image/jpeg", "receipt.pdf"),
        ("image/gif", "receipt.gif"),
        ("application/pdf", "receipt.jpg"),
    ],
)
def test_rejects_unsupported_type_or_extension(content_type, filename):
    with pytest.raises(UnsupportedFileType) as exc:
        receipt_storage.validate_image(JPEG, content_type, filename)
    assert exc.value.status_code == 415
    assert exc.value.code == "unsupported_file_type"


def test_rejects_content_that_is_not_an_image():
    with pytest.raises(UnsupportedFileType):
        receipt_storage.validate_image(b"%PDF-1.7 fake", "image/jpeg", "receipt.jpg")


def test_generic_content_type_uses_extension_and_magic_bytes():
    image = receipt_storage.validate_image(HEIC, "application/octet-stream", "IMG_0001.HEIC")
    assert image.mime_type == "image/heic"
    assert image.extension == ".heic"
    image = receipt_storage.validate_image(PNG, "", "scan.png")
    assert image.mime_type == "image/png"


def test_stored_mime_follows_content_not_declared_type():
    image = receipt_storage.validate_image(PNG, "image/jpeg", "photo.jpg")
    assert image.mime_type == "image/png"
    assert image.extension == ".png"


def test_size_limit_is_10mb():
    at_limit = JPEG + b"\x00" * (receipt_storage.MAX_RECEIPT_BYTES - len(JPEG))
    assert receipt_storage.validate_image(at_limit, "image/jpeg", "a.jpg").size == 10 * 1024 * 1024
    with pytest.raises(FileTooLarge) as exc:
        receipt_storage.validate_image(at_limit + b"\x00", "image/jpeg", "a.jpg")
    assert exc.value.status_code == 413
    assert "10MB" in exc.value.detail


def test_empty_file_rejected():
    with pytest.raises(DomainError) as exc:
        receipt_storage.validate_image(b"", "image/jpeg", "a.jpg")
    assert exc.value.code == "empty_file"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("receipt.jpg", "receipt.jpg"),
        ("../../etc/passwd.jpg", "passwd.jpg"),
        (r"C:\Users\me\Pictures\bill.png", "bill.png"),
        ("", "receipt"),
        (None, "receipt"),
        ("a" * 300 + ".jpg", "a" * 255),
    ],
)
def test_clean_filename(raw, expected):
    assert receipt_storage.clean_filename(raw) == expected


def test_relative_path_uses_uuid_and_month():
    receipt_id = uuid.UUID("3f1c9a62-8d2e-4f61-9b7a-0c2d4e6f8a10")
    assert (
        receipt_storage.relative_path(receipt_id, date(2026, 10, 5), ".jpg")
        == "receipts/2026/10/3f1c9a62-8d2e-4f61-9b7a-0c2d4e6f8a10.jpg"
    )


@pytest.mark.parametrize(
    "relative", ["../secret.jpg", "receipts/../../x.jpg", "/etc/passwd", "C:/Windows/x.jpg"]
)
def test_resolve_path_blocks_escape(relative):
    root = Path(__file__).resolve().parent
    with pytest.raises(DomainError) as exc:
        receipt_storage.resolve_path(relative, root)
    assert exc.value.code == "invalid_file_path"


def test_resolve_path_inside_root():
    root = Path(__file__).resolve().parent
    path = receipt_storage.resolve_path("receipts/2026/10/a.jpg", root)
    assert path == root / "receipts" / "2026" / "10" / "a.jpg"


def test_upload_root_relative_to_backend(monkeypatch):
    from app.core.config import BACKEND_DIR, Settings

    monkeypatch.setattr(
        receipt_storage, "get_settings", lambda: Settings(upload_dir=Path("./uploads"))
    )
    assert receipt_storage.upload_root() == (BACKEND_DIR / "uploads").resolve()


def _heic_bytes() -> bytes:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), (200, 30, 30)).save(buffer, format="HEIF", quality=60)
    return buffer.getvalue()


def test_vision_payload_converts_heic_to_jpeg():
    heic = _heic_bytes()
    assert receipt_storage.sniff_image_type(heic) == "image/heic"
    content, mime = receipt_storage.vision_payload(heic, "image/heic")
    assert mime == "image/jpeg"
    assert receipt_storage.sniff_image_type(content) == "image/jpeg"


def test_vision_payload_keeps_jpeg():
    assert receipt_storage.vision_payload(JPEG, "image/jpeg") == (JPEG, "image/jpeg")


def test_broken_heic_is_unreadable():
    with pytest.raises(DomainError) as exc:
        receipt_storage.vision_payload(HEIC, "image/heic")
    assert exc.value.code == "image_unreadable"
