"""Knowledge base / RAG (Phase 16) — ingest tài liệu và tìm đoạn liên quan (deterministic).

- `ingest_path`: đọc `.md` / `.pdf` trong thư mục (hoặc 1 file) → chia đoạn → embed (`embedder` do
  caller truyền, `services` không import `ai`) → lưu. Idempotent theo `content_hash`: file không đổi
  → bỏ qua (không gọi AI); nội dung đổi → thay toàn bộ đoạn; cùng nội dung ở file khác → bỏ qua.
- `search`: embed câu hỏi → top-k đoạn theo cosine distance; bỏ đoạn tương đồng thấp.
"""

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR
from app.core.errors import DomainError, NotFoundError
from app.models import KnowledgeChunk, KnowledgeDocument
from app.repositories import knowledge_repository
from app.schemas.coach import KnowledgeToolItem, SearchKnowledgeInput, SearchKnowledgeOutput
from app.schemas.knowledge import (
    KnowledgeChunkRead,
    KnowledgeDocumentList,
    KnowledgeDocumentRead,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)
from app.services import knowledge_chunking
from app.services.embedding_service import Embedder, current_model
from app.services.knowledge_chunking import SUPPORTED_SUFFIXES

logger = logging.getLogger(__name__)

DEFAULT_KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"
MAX_FILE_BYTES = 5 * 1024 * 1024
# Đoạn có độ tương đồng thấp hơn ngưỡng này không được coi là nguồn (tránh trích nguồn sai).
MIN_KNOWLEDGE_SCORE = 0.3


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


def _base_for(path: Path) -> Path:
    """Gốc để tính đường dẫn nguồn: `backend/` nếu nằm trong đó, ngược lại thư mục cha."""
    resolved = path.resolve()
    backend = BACKEND_DIR.resolve()
    return backend if resolved.is_relative_to(backend) else resolved.parent


def _base_root(base: Path | None, path: Path) -> Path:
    return (base or _base_for(path)).resolve()


def source_name(path: Path, base: Path | None = None) -> str:
    """Đường dẫn lưu trong DB (posix, tương đối `base`) — không lưu đường dẫn tuyệt đối của máy."""
    resolved = path.resolve()
    base = (base or _base_for(path)).resolve()
    if resolved.is_relative_to(base):
        return resolved.relative_to(base).as_posix()
    return resolved.name


def resolve_ingest_path(raw: str | None, *, root: Path = BACKEND_DIR) -> Path:
    """Đường dẫn ingest qua API: chỉ cho phép trong `backend/` (chống path traversal)."""
    root = root.resolve()
    target = (root / raw).resolve() if raw else DEFAULT_KNOWLEDGE_DIR.resolve()
    if not target.is_relative_to(root):
        raise DomainError("Chỉ được ingest tài liệu nằm trong thư mục backend", "invalid_path")
    if not target.exists():
        raise DomainError(f"Không tìm thấy {raw or 'knowledge'}", "path_not_found")
    return target


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_SUFFIXES else []
    return sorted(
        p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def ingest_file(
    db: Session, path: Path, embedder: Embedder, *, base: Path | None = None
) -> tuple[str, int]:
    """Ingest 1 file → (`created | updated | unchanged | skipped`, số đoạn). Commit nếu ghi."""
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise DomainError(f"{path.name} lớn hơn 5MB", "file_too_large")
    digest = knowledge_chunking.content_hash(raw)
    source = source_name(path, base)
    existing = knowledge_repository.get_by_source(db, source)
    if existing is not None and existing.content_hash == digest:
        return "unchanged", len(existing.chunks)
    same_content = knowledge_repository.get_by_hash(db, digest)
    if same_content is not None and same_content.source != source:
        if existing is None and not (_base_root(base, path) / same_content.source).exists():
            # File cũ không còn, nội dung y hệt → đổi tên: giữ đoạn + embedding, chỉ đổi nguồn.
            same_content.source = source
            same_content.meta = {**(same_content.meta or {}), "source_path": source}
            for chunk in same_content.chunks:
                chunk.meta = {**(chunk.meta or {}), "source_path": source}
            db.commit()
            return "updated", len(same_content.chunks)
        logger.info("knowledge skip duplicate source=%s of=%s", source, same_content.source)
        return "skipped", 0

    loaded = knowledge_chunking.load_document(path, raw)
    chunks = knowledge_chunking.chunk_document(loaded)
    if not chunks:
        raise DomainError(f"{path.name} không có nội dung", "empty_document")
    embedded = embedder([knowledge_chunking.embedding_text(loaded.title, c) for c in chunks])
    if len(embedded.vectors) != len(chunks):
        raise DomainError("Dịch vụ embedding trả thiếu kết quả", "embedding_mismatch")

    status = "created"
    if existing is not None:
        knowledge_repository.delete_document(db, existing)
        status = "updated"
    model = current_model()
    document = KnowledgeDocument(
        title=loaded.title,
        source=source,
        source_type=loaded.source_type,
        content_hash=digest,
        meta={**loaded.metadata, "source_path": source},
    )
    document.chunks = [
        KnowledgeChunk(
            chunk_index=c.index,
            heading=c.heading,
            content=c.content,
            embedding=vector,
            model=model,
            meta={
                "source_path": source,
                "heading_path": c.heading_path,
                "headings": c.headings,
                "tags": loaded.metadata.get("tags", []),
                "language": loaded.metadata.get("language", "vi"),
                "token_estimate": c.tokens,
                **({"pages": c.pages} if c.pages else {}),
            },
        )
        for c, vector in zip(chunks, embedded.vectors, strict=True)
    ]
    knowledge_repository.add(db, document)
    db.commit()
    return status, len(chunks)


def ingest_path(
    db: Session, path: Path, embedder: Embedder, *, prune: bool = False
) -> IngestReport:
    """Ingest mọi `.md` / `.pdf` trong `path`. Lỗi đọc file → ghi vào `errors`, tiếp tục; lỗi AI
    (`AIUnavailable`) → raise (các file trước đã commit)."""
    if not path.exists():
        raise DomainError(f"Không tìm thấy {path}", "path_not_found")
    base = _base_for(path)
    report = IngestReport()
    seen: set[str] = set()
    for file in _files(path):
        seen.add(source_name(file, base))
        try:
            status, count = ingest_file(db, file, embedder, base=base)
        except DomainError as exc:
            if exc.code.startswith("AI_"):
                raise
            db.rollback()
            report.errors.append(f"{file.name}: {exc.detail}")
            report.skipped += 1
            continue
        report.documents += 1
        report.chunks += count
        setattr(report, status, getattr(report, status) + 1)
    if prune and path.is_dir():
        prefix = source_name(path, base).rstrip("/") + "/"
        for document in knowledge_repository.list_documents(db):
            if document.source.startswith(prefix) and document.source not in seen:
                knowledge_repository.delete_document(db, document)
                report.removed += 1
        db.commit()
    return report


# ---------- đọc / tìm ----------


def _result(chunk: KnowledgeChunk, score: float) -> KnowledgeSearchResult:
    doc = chunk.document
    return KnowledgeSearchResult(
        chunk_id=chunk.id,
        document_id=doc.id,
        title=doc.title,
        heading=chunk.heading,
        source=doc.source,
        content=chunk.content,
        score=round(score, 4),
        citation=knowledge_chunking.citation(doc.title, chunk.heading, doc.source),
    )


def search(
    db: Session, query: str, embedder: Embedder, *, limit: int = 5
) -> KnowledgeSearchResponse:
    cleaned = " ".join(query.split())
    if not cleaned:
        raise DomainError("Bạn nhập câu hỏi cần tra nhé", "empty_query")
    vector = embedder([cleaned]).vectors[0]
    rows = knowledge_repository.nearest_chunks(db, vector, limit=limit)
    results = [_result(c, 1.0 - d) for c, d in rows if 1.0 - d >= MIN_KNOWLEDGE_SCORE]
    return KnowledgeSearchResponse(query=cleaned, results=results)


def search_for_coach(
    db: Session, data: SearchKnowledgeInput, embedder: Embedder
) -> SearchKnowledgeOutput:
    """Tool Coach `search_knowledge` (chỉ đọc)."""
    response = search(db, data.query, embedder, limit=data.limit)
    return SearchKnowledgeOutput(
        query=response.query,
        results=[KnowledgeToolItem(**r.model_dump()) for r in response.results],
        note=(
            "Chỉ dùng nội dung trong các đoạn này cho phần kiến thức; chép đúng `citation` vào "
            "mục Nguồn cho đoạn đã dùng."
            if response.results
            else "Không tìm thấy nguồn đủ tin cậy trong thư viện kiến thức — nói rõ điều này, "
            "không tự trả lời phần kiến thức và không ghi nguồn."
        ),
    )


def get_chunk(db: Session, chunk_id: uuid.UUID) -> KnowledgeChunkRead:
    chunk = knowledge_repository.get_chunk(db, chunk_id)
    if chunk is None:
        raise NotFoundError("Không tìm thấy đoạn kiến thức", "knowledge_chunk_not_found")
    base = _result(chunk, 1.0)
    return KnowledgeChunkRead(
        **base.model_dump(exclude={"score"}),
        score=1.0,
        chunk_index=chunk.chunk_index,
        headings=list((chunk.meta or {}).get("headings") or []),
        source_type=chunk.document.source_type,
    )


def list_documents(db: Session) -> KnowledgeDocumentList:
    counts = knowledge_repository.chunk_counts(db)
    return KnowledgeDocumentList(
        items=[
            KnowledgeDocumentRead(
                id=d.id,
                title=d.title,
                source=d.source,
                source_type=d.source_type,
                chunk_count=counts.get(d.id, 0),
                tags=list((d.meta or {}).get("tags") or []),
            )
            for d in knowledge_repository.list_documents(db)
        ]
    )
