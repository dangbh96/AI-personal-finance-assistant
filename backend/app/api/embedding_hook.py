"""Embed giao dịch ngay sau khi lưu (Phase 15) — best-effort, không bao giờ làm request lỗi.

Gọi **sau** khi đã dựng response (lỗi embedding có thể rollback session → object bị expire).
"""

import uuid
from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.ai import embeddings
from app.services import embedding_service


def index_transactions(db: Session, transaction_ids: Iterable[uuid.UUID]) -> int:
    return embedding_service.embed_transactions_best_effort(
        db, list(transaction_ids), embeddings.embed_documents
    )


def index_import_batch(db: Session, batch_id: uuid.UUID) -> int:
    ids = embedding_service.import_batch_transaction_ids(db, batch_id)
    return index_transactions(db, ids)
