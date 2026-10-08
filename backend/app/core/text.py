import re
import unicodedata


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt: "Thú cưng Đỏ" -> "Thu cung Do"."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def slugify(text: str, max_length: int = 60) -> str:
    """Slug ASCII snake_case: "Quà tặng & hiếu hỉ" -> "qua_tang_hieu_hi"."""
    slug = re.sub(r"[^a-z0-9]+", "_", strip_accents(text).lower()).strip("_")
    return slug[:max_length].rstrip("_")
