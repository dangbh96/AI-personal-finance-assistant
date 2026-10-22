"""Đọc & chia đoạn tài liệu kiến thức (Phase 16) — hàm thuần, không DB / AI.

- `load_markdown` / `load_pdf` → `LoadedDocument` (tiêu đề, khối văn bản kèm đường dẫn heading).
- `chunk_document` → các đoạn ~500–800 token **ước lượng** (`estimate_tokens` = số ký tự / 3, chưa
  dùng tokenizer thật), cắt ưu tiên ở ranh giới mục (`##`); đoạn dài bị cắt giữa mục thì đoạn sau
  lặp lại ~100 token cuối của đoạn trước (overlap).
- `embedding_text`: chuỗi đem embed = tiêu đề + đường dẫn heading + nội dung.
"""

import hashlib
import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.errors import DomainError

MAX_TOKENS = 800
MIN_TOKENS = 500
OVERLAP_TOKENS = 100
CHARS_PER_TOKEN = 3
SUPPORTED_SUFFIXES = {".md": "markdown", ".markdown": "markdown", ".pdf": "pdf"}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_RE = re.compile(r"(?<=[.!?…:;])\s+|\n+")
_SPACE_RE = re.compile(r"[ \t]+")


def estimate_tokens(text: str) -> int:
    """Ước lượng số token (~3 ký tự tiếng Việt có dấu / token)."""
    return math.ceil(len(text.strip()) / CHARS_PER_TOKEN) if text.strip() else 0


def content_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Block:
    text: str
    heading_path: tuple[str, ...]
    section_start: bool = False
    page: int | None = None


@dataclass
class LoadedDocument:
    title: str
    source_type: str
    blocks: list[Block]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    index: int
    heading: str | None
    heading_path: list[str]
    content: str
    tokens: int
    pages: list[int] = field(default_factory=list)
    # Mọi heading mục có trong đoạn (đoạn có thể gồm nhiều mục ngắn).
    headings: list[str] = field(default_factory=list)


# ---------- markdown ----------


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            meta: dict[str, str] = {}
            for line in lines[1:end]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip().lower()] = value.strip().strip("\"'")
            return meta, "\n".join(lines[end + 1 :])
    return {}, text


def _clean_inline(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def load_markdown(raw: bytes, *, fallback_title: str) -> LoadedDocument:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DomainError("File markdown phải là UTF-8", "invalid_encoding") from exc
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    meta, body = _front_matter(text)

    title = meta.get("title") or ""
    path: list[tuple[int, str]] = []
    blocks: list[Block] = []
    current: list[str] = []
    pending_start = False

    def flush() -> None:
        nonlocal current, pending_start
        joined = "\n".join(line.rstrip() for line in current).strip()
        if joined:
            blocks.append(Block(joined, tuple(h for _, h in path), pending_start))
            pending_start = False
        current = []

    for line in body.split("\n"):
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level, name = len(heading.group(1)), _clean_inline(heading.group(2))
            if level == 1:
                title = title or name
                path = []
            else:
                path = [(lvl, h) for lvl, h in path if lvl < level] + [(level, name)]
            pending_start = True
        elif not line.strip():
            flush()
        else:
            current.append(line)
    flush()

    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    return LoadedDocument(
        title=title or fallback_title,
        source_type="markdown",
        blocks=blocks,
        metadata={"tags": tags, "language": meta.get("language", "vi")},
    )


# ---------- pdf ----------


def load_pdf(raw: bytes, *, fallback_title: str) -> LoadedDocument:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        info_title = (reader.metadata.title if reader.metadata else None) or ""
    except (PdfReadError, ValueError, KeyError) as exc:
        raise DomainError("Không đọc được file PDF", "unreadable_pdf") from exc

    blocks: list[Block] = []
    for number, text in enumerate(pages, start=1):
        text = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for i, paragraph in enumerate(paragraphs):
            joined = _clean_inline(paragraph.replace("\n", " "))
            blocks.append(Block(joined, (f"Trang {number}",), i == 0, number))
    if not blocks:
        raise DomainError("PDF không có lớp chữ (có thể là ảnh scan)", "empty_pdf")
    return LoadedDocument(
        title=_clean_inline(info_title) or fallback_title,
        source_type="pdf",
        blocks=blocks,
        metadata={"tags": [], "language": "vi", "page_count": len(pages)},
    )


def load_document(path: Path, raw: bytes | None = None) -> LoadedDocument:
    source_type = SUPPORTED_SUFFIXES.get(path.suffix.lower())
    if source_type is None:
        raise DomainError(f"Không hỗ trợ file {path.suffix}", "unsupported_file_type")
    raw = raw if raw is not None else path.read_bytes()
    fallback = path.stem.replace("-", " ").replace("_", " ").strip() or path.name
    if source_type == "pdf":
        return load_pdf(raw, fallback_title=fallback)
    return load_markdown(raw, fallback_title=fallback)


# ---------- chunking ----------


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _split_long(block: Block, max_tokens: int) -> list[Block]:
    """Khối dài hơn `max_tokens` → nhiều khối theo câu (câu quá dài → cắt theo ký tự)."""
    if estimate_tokens(block.text) <= max_tokens:
        return [block]
    parts: list[str] = []
    current = ""
    for sentence in _sentences(block.text):
        while estimate_tokens(sentence) > max_tokens:
            cut = max_tokens * CHARS_PER_TOKEN
            parts.append(sentence[:cut])
            sentence = sentence[cut:]
        candidate = f"{current} {sentence}".strip()
        if current and estimate_tokens(candidate) > max_tokens:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    return [
        Block(p, block.heading_path, block.section_start and i == 0, block.page)
        for i, p in enumerate(parts)
    ]


def _overlap_tail(blocks: list[Block], overlap_tokens: int) -> str:
    """~`overlap_tokens` cuối của các khối (theo câu trọn vẹn)."""
    sentences = [s for b in blocks for s in _sentences(b.text)]
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        tokens = estimate_tokens(sentence)
        if tail and total + tokens > overlap_tokens:
            break
        if not tail and tokens > overlap_tokens:
            tail.append(sentence[-overlap_tokens * CHARS_PER_TOKEN :])
            break
        tail.append(sentence)
        total += tokens
    return " ".join(reversed(tail))


def chunk_document(
    doc: LoadedDocument,
    *,
    max_tokens: int = MAX_TOKENS,
    min_tokens: int = MIN_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    blocks = [b for block in doc.blocks for b in _split_long(block, max_tokens - overlap_tokens)]
    groups: list[tuple[list[Block], str]] = []  # (khối, phần overlap đứng đầu)
    current: list[Block] = []
    prefix = ""

    def size(items: list[Block], head: str) -> int:
        return estimate_tokens("\n\n".join([head, *(b.text for b in items)]))

    for block in blocks:
        if current:
            at_section = block.section_start and size(current, prefix) >= min_tokens
            too_big = size([*current, block], prefix) > max_tokens
            if at_section or too_big:
                groups.append((current, prefix))
                # Cắt giữa mục → lặp lại đuôi đoạn trước; cắt ở ranh giới mục → heading đủ ngữ cảnh.
                prefix = "" if block.section_start else _overlap_tail(current, overlap_tokens)
                current = []
        current.append(block)
    if current:
        groups.append((current, prefix))

    # Đoạn cuối quá ngắn → gộp vào đoạn trước nếu vẫn ≤ max_tokens.
    if len(groups) >= 2:
        last_blocks, last_prefix = groups[-1]
        prev_blocks, prev_prefix = groups[-2]
        if size(last_blocks, "") < min_tokens // 3 and (
            size(prev_blocks + last_blocks, prev_prefix) <= max_tokens
        ):
            groups[-2:] = [(prev_blocks + last_blocks, prev_prefix)]

    chunks = []
    for index, (items, head) in enumerate(groups):
        path = list(items[0].heading_path)
        content = "\n\n".join([head, *(b.text for b in items)] if head else [b.text for b in items])
        chunks.append(
            Chunk(
                index=index,
                heading=path[-1] if path else None,
                heading_path=path,
                content=content,
                tokens=estimate_tokens(content),
                pages=sorted({b.page for b in items if b.page is not None}),
                headings=list(dict.fromkeys(b.heading_path[-1] for b in items if b.heading_path)),
            )
        )
    return chunks


def embedding_text(title: str, chunk: Chunk) -> str:
    header = " › ".join([title, *chunk.heading_path])
    return f"{header}\n\n{chunk.content}"


def citation(title: str, heading: str | None, source: str) -> str:
    return f"{title} — {heading} ({source})" if heading else f"{title} ({source})"
