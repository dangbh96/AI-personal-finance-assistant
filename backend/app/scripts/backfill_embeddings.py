"""Tạo embedding cho giao dịch chưa có / đã cũ (Phase 15).

    python -m app.scripts.backfill_embeddings [--batch-size 100] [--limit N] [--force]

- Duyệt toàn bộ bảng `transactions` theo lô; chỉ gọi OpenAI cho giao dịch thiếu embedding hoặc
  có nội dung (ghi chú / danh mục / khoảng tiền / loại) hay model khác lần embed trước.
- `--force`: embed lại tất cả. `--limit`: dừng sau khi embed N giao dịch.
- Chạy lại an toàn (idempotent). Cần `OPENAI_API_KEY`.
"""

import argparse
import sys

from app.ai import embeddings
from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.services import embedding_service


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Tạo embedding cho giao dịch thiếu / cũ.")
    parser.add_argument("--batch-size", type=int, default=embedding_service.DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="Embed tối đa N giao dịch")
    parser.add_argument("--force", action="store_true", help="Embed lại mọi giao dịch")
    args = parser.parse_args(argv)

    def progress(scanned: int, processed: int) -> None:
        print(f"  đã duyệt {scanned} giao dịch, embed {processed}")

    with SessionLocal() as db:
        try:
            report = embedding_service.backfill(
                db,
                embeddings.embed_documents,
                batch_size=args.batch_size,
                limit=args.limit,
                force=args.force,
                on_batch=progress,
            )
        except DomainError as exc:
            print(f"Lỗi: {exc.detail} ({exc.code})", file=sys.stderr)
            return 1
    print(
        f"Xong: duyệt {report.scanned} giao dịch, embed {report.processed}, "
        f"giữ nguyên {report.unchanged}, còn thiếu {report.remaining_missing}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
