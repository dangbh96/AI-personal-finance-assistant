"""Chuẩn hoá câu / pattern cho classification memory (Phase 3) — deterministic, không dùng AI.

    "Mua giày MLB 1.8 triệu" → normalize → "mua giay mlb" → keyword → "giay"
    "Sửa laptop 900k"        → normalize → "sua laptop"   → keyword → "sua laptop"

Pattern khớp câu khi **mọi token** của pattern có trong câu (không cần liền nhau). Pattern chỉ gồm
từ chung chung ("mua", "tien"…) bị coi là quá rộng: không dùng để áp dụng thẳng.
"""

import re
import unicodedata

from app.core.text import strip_accents
from app.services.amount_text import amount_spans

# Từ chung chung (động từ phổ biến, đại từ, lượng từ, thời gian) — không làm keyword.
# Lưu ý: bỏ dấu làm trùng từ ("nhà"/"nha", "sữa"/"sửa") nên không đưa "nha" vào đây.
# fmt: off
STOPWORDS = frozenset({
    # động từ chung
    "mua", "an", "uong", "di", "dat", "tra", "nop", "dong", "chuyen", "nhan", "lay", "gui",
    "chi", "tieu", "het", "mat", "duoc", "bi", "coi", "xem",
    # đại từ, hư từ
    "tao", "minh", "em", "anh", "ban", "toi", "chung", "cho", "voi", "ve", "va", "cua",
    "la", "tai", "mot", "nua", "them", "cung", "nhe", "roi", "luon", "thi", "ma",
    "nay", "do", "kia", "moi", "cu",
    # lượng từ
    "cai", "con", "chiec", "doi", "ly", "coc", "phan", "suat", "hop", "goi", "lan",
    # thời gian
    "hom", "qua", "sang", "trua", "chieu", "dem", "sau", "truoc", "tuan", "thang", "nam",
    "ngay", "thu", "cn", "mai",
})
# fmt: on

# Từ chỉ có nghĩa khi đi kèm từ ngay sau: "tiền nhà", "sửa laptop", "phí ship".
HEAD_WORDS = frozenset({"tien", "phi", "sua", "thue", "sieu"})

_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def _without_amounts(text: str) -> str:
    normalized = strip_accents(unicodedata.normalize("NFC", text)).lower()
    for start, end in reversed(amount_spans(normalized)):
        normalized = f"{normalized[:start]} {normalized[end:]}"
    return normalized


def normalize_text(text: str) -> str:
    """Lowercase, bỏ dấu, bỏ số tiền (kèm đơn vị), dấu câu, số trơn và token 1 ký tự."""
    tokens = _NON_WORD_RE.sub(" ", _without_amounts(text)).split()
    return " ".join(t for t in tokens if len(t) > 1 and not t.isdigit())


def has_digits_besides_amounts(text: str) -> bool:
    """Còn chữ số sau khi bỏ số tiền (ngày "5/10", giờ "7h"…)."""
    return any(ch.isdigit() for ch in _without_amounts(text))


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


def normalize_pattern(pattern: str) -> str:
    """Pattern lưu DB: như `normalize_text` nhưng bỏ từ chung ("cafe với khách" → "cafe khach")."""
    return " ".join(t for t in tokenize(pattern) if t not in STOPWORDS)


def extract_keyword(text: str | None) -> str | None:
    """Keyword chính của câu để học preference: từ có nghĩa đầu tiên (+ từ ngay sau nếu là
    HEAD_WORDS)."""
    if not text:
        return None
    tokens = tokenize(text)
    for i, token in enumerate(tokens):
        if token in STOPWORDS:
            continue
        if token in HEAD_WORDS:
            following = tokens[i + 1] if i + 1 < len(tokens) else None
            if following is None or following in STOPWORDS:
                continue
            return f"{token} {following}"
        return token
    return None


def is_specific(pattern: str) -> bool:
    """Pattern đủ cụ thể để áp dụng thẳng: có ít nhất 1 token ≥ 2 ký tự không phải từ chung."""
    return any(len(t) >= 2 and t not in STOPWORDS and t not in HEAD_WORDS for t in pattern.split())


def pattern_matches(pattern: str, tokens: set[str]) -> bool:
    parts = pattern.split()
    return bool(parts) and all(p in tokens for p in parts)


def overlap(pattern: str, tokens: set[str]) -> int:
    """Số token có nghĩa của pattern xuất hiện trong câu (để chọn few-shot liên quan)."""
    return sum(1 for p in pattern.split() if p in tokens and p not in STOPWORDS)
