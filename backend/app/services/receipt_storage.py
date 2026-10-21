"""Lưu ảnh hoá đơn trên đĩa (Phase 13) — deterministic, không AI.

- Validate content type + đuôi file + kích thước (≤ 10 MB) + magic bytes (nội dung thật là ảnh).
- Tên file là uuid (id của receipt), lưu dưới `UPLOAD_DIR/receipts/YYYY/MM/`; DB chỉ giữ đường dẫn
  tương đối dạng posix. Mọi đường dẫn đọc ra đều được kiểm tra nằm trong `UPLOAD_DIR`.
- HEIC / HEIF đổi sang JPEG (Pillow + pillow-heif) khi cần gửi model vision hoặc xem trước trên
  trình duyệt; file gốc giữ nguyên.
"""

import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import DomainError

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_FILENAME_LENGTH = 255

# mime → đuôi file dùng khi lưu.
MIME_EXTENSIONS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})
# Trình duyệt hay gửi HEIC với type rỗng / octet-stream → dựa vào đuôi + magic bytes.
GENERIC_CONTENT_TYPES = frozenset({"", "application/octet-stream"})
CONVERT_TO_JPEG = frozenset({"image/heic", "image/heif"})

_HEIC_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"})
_HEIF_BRANDS = frozenset({b"mif1", b"msf1"})


class FileTooLarge(DomainError):
    status_code = 413

    def __init__(self) -> None:
        super().__init__(
            "Ảnh vượt quá dung lượng tối đa 10MB. Bạn chụp lại hoặc giảm kích thước ảnh giúp nhé.",
            "file_too_large",
        )


class UnsupportedFileType(DomainError):
    status_code = 415

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            detail or "Chỉ nhận ảnh JPEG, PNG, WEBP hoặc HEIC/HEIF (tối đa 10MB).",
            "unsupported_file_type",
        )


@dataclass(frozen=True)
class ValidatedImage:
    content: bytes
    mime_type: str
    extension: str
    sha256: str
    original_filename: str

    @property
    def size(self) -> int:
        return len(self.content)


def upload_root() -> Path:
    """`UPLOAD_DIR` tuyệt đối (đường dẫn tương đối tính từ thư mục `backend/`)."""
    root = Path(get_settings().upload_dir)
    if not root.is_absolute():
        root = BACKEND_DIR / root
    return root.resolve()


def clean_filename(filename: str | None) -> str:
    """Chỉ giữ tên file (bỏ thư mục, cả kiểu Windows), cắt ≤ 255 ký tự."""
    name = PureWindowsPath(PurePosixPath(filename or "").name).name.strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "receipt")[:MAX_FILENAME_LENGTH]


def extension_of(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def sniff_image_type(content: bytes) -> str | None:
    """Nhận dạng ảnh theo magic bytes; `None` nếu không phải định dạng được nhận."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12]
        if brand in _HEIC_BRANDS:
            return "image/heic"
        if brand in _HEIF_BRANDS:
            return "image/heif"
    return None


def check_declared_type(content_type: str | None, filename: str) -> None:
    """Kiểm tra trước khi đọc nội dung: content type + đuôi file."""
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in MIME_EXTENSIONS and declared not in GENERIC_CONTENT_TYPES:
        raise UnsupportedFileType()
    if extension_of(filename) not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileType()


def validate_image(
    content: bytes, content_type: str | None, filename: str | None
) -> ValidatedImage:
    """Validate upload (đã đọc tối đa `MAX_RECEIPT_BYTES + 1` byte). Lỗi → 413 / 415 / 422."""
    name = clean_filename(filename)
    check_declared_type(content_type, name)
    if len(content) > MAX_RECEIPT_BYTES:
        raise FileTooLarge()
    if not content:
        raise DomainError("File ảnh rỗng.", "empty_file")
    sniffed = sniff_image_type(content)
    if sniffed is None:
        raise UnsupportedFileType(
            "Nội dung file không phải ảnh JPEG, PNG, WEBP hoặc HEIC/HEIF hợp lệ."
        )
    return ValidatedImage(
        content=content,
        mime_type=sniffed,
        extension=MIME_EXTENSIONS[sniffed],
        sha256=hashlib.sha256(content).hexdigest(),
        original_filename=name,
    )


def relative_path(receipt_id: uuid.UUID, uploaded_on: date, extension: str) -> str:
    """`receipts/YYYY/MM/{uuid}.ext` (posix, tương đối trong `UPLOAD_DIR`)."""
    return f"receipts/{uploaded_on.year:04d}/{uploaded_on.month:02d}/{receipt_id}{extension}"


def resolve_path(relative: str, root: Path | None = None) -> Path:
    """Đường dẫn tuyệt đối của file, chặn thoát khỏi `UPLOAD_DIR` (`..`, đường dẫn tuyệt đối)."""
    root = (root or upload_root()).resolve()
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts or PureWindowsPath(relative).drive:
        raise DomainError("Đường dẫn file không hợp lệ", "invalid_file_path")
    path = (root / Path(*rel.parts)).resolve()
    if not path.is_relative_to(root):
        raise DomainError("Đường dẫn file không hợp lệ", "invalid_file_path")
    return path


def save_file(relative: str, content: bytes) -> Path:
    path = resolve_path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def read_file(relative: str) -> bytes | None:
    path = resolve_path(relative)
    return path.read_bytes() if path.is_file() else None


def delete_file(relative: str) -> None:
    path = resolve_path(relative)
    path.unlink(missing_ok=True)


def to_jpeg(content: bytes) -> bytes:
    """Đổi ảnh (HEIC/HEIF…) sang JPEG. Lỗi giải mã → `DomainError('image_unreadable')`."""
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    try:
        with Image.open(io.BytesIO(content)) as image:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=90)
            return out.getvalue()
    except Exception as exc:  # Pillow raise nhiều loại lỗi khác nhau khi ảnh hỏng.
        raise DomainError(
            "Không giải mã được ảnh hoá đơn (file hỏng hoặc định dạng chưa hỗ trợ).",
            "image_unreadable",
        ) from exc


def vision_payload(content: bytes, mime_type: str) -> tuple[bytes, str]:
    """Ảnh gửi model vision: JPEG/PNG/WEBP giữ nguyên, HEIC/HEIF đổi sang JPEG."""
    if mime_type in CONVERT_TO_JPEG:
        return to_jpeg(content), "image/jpeg"
    return content, mime_type
