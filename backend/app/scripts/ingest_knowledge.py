"""Ingest knowledge base (Phase 16).

    python -m app.scripts.ingest_knowledge [knowledge/] [--prune]

Đọc mọi `.md` / `.pdf` trong thư mục (mặc định `backend/knowledge/`), chia đoạn ~500–800 token
(ước lượng), embed bằng `OPENAI_EMBEDDING_MODEL` và lưu `knowledge_documents` / `knowledge_chunks`.
Chạy lại an toàn: file không đổi (`content_hash`) được bỏ qua, file đổi được thay toàn bộ đoạn.
`--prune` xoá tài liệu đã ingest từ thư mục này mà file không còn. Cần `OPENAI_API_KEY`.
"""

import argparse
import sys
from pathlib import Path

from app.ai import embeddings
from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.services import knowledge_service


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Ingest tài liệu kiến thức cho Coach (RAG).")
    parser.add_argument(
        "path", nargs="?", default=str(knowledge_service.DEFAULT_KNOWLEDGE_DIR), type=Path
    )
    parser.add_argument("--prune", action="store_true", help="Xoá tài liệu không còn file")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        try:
            report = knowledge_service.ingest_path(
                db, args.path, embeddings.embed_knowledge, prune=args.prune
            )
        except DomainError as exc:
            print(f"Lỗi: {exc.detail} ({exc.code})", file=sys.stderr)
            return 1
    for error in report.errors:
        print(f"  ! {error}", file=sys.stderr)
    print(
        f"Xong: {report.documents} tài liệu, {report.chunks} đoạn "
        f"(mới {report.created}, cập nhật {report.updated}, giữ nguyên {report.unchanged}, "
        f"bỏ qua {report.skipped}, xoá {report.removed})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
