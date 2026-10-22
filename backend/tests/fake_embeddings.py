"""Embedding giả, deterministic cho test (không gọi OpenAI).

Vector = bag-of-words băm (mỗi từ đã bỏ dấu → 1 chiều) + "khái niệm" chung cho các cụm đồng nghĩa
(`CONCEPTS`) với trọng số lớn hơn → "ăn ngoài" gần "nhà hàng", "bún chả"; "đi lại" gần "grab",
"xăng". Chuẩn hoá L2 để cosine distance có nghĩa.
"""

import hashlib
import math
import re

from app.ai.openai_client import EmbeddingResult
from app.core.text import strip_accents

DIM = 1536
FAKE_MODEL = "text-embedding-3-small"

CONCEPTS: dict[str, tuple[str, ...]] = {
    "eat_out": ("an ngoai", "nha hang", "quan nuong", "bun cha", "lau", "pho", "an trua"),
    "travel": ("di lai", "grab", "xang", "xe bus", "taxi", "gui xe"),
    "coffee": ("ca phe", "cafe", "highlands", "tra sua"),
    "shopping": ("mua sam", "quan ao", "giay", "shopee"),
}
CONCEPT_WEIGHT = 3.0


def _index(token: str) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % DIM


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(text).lower()).strip()


def fake_vector(text: str) -> list[float]:
    vec = [0.0] * DIM
    norm = _normalize(text)
    padded = f" {norm} "
    for token in norm.split():
        vec[_index(token)] += 1.0
    for concept, phrases in CONCEPTS.items():
        if any(f" {p} " in padded for p in phrases):
            vec[_index(f"concept:{concept}")] += CONCEPT_WEIGHT
    length = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / length for v in vec]


def fake_embed_raw(*, model: str, inputs: list[str], timeout: float) -> EmbeddingResult:
    return EmbeddingResult(
        vectors=[fake_vector(t) for t in inputs], model=model, prompt_tokens=len(inputs) * 10
    )
