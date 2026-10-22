import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportBatch, ImportMappingProfile


def get(db: Session, batch_id: uuid.UUID) -> ImportBatch | None:
    return db.get(ImportBatch, batch_id)


def get_by_file_hash(db: Session, file_hash: str) -> ImportBatch | None:
    return db.scalar(select(ImportBatch).where(ImportBatch.file_hash == file_hash))


def add(db: Session, batch: ImportBatch) -> ImportBatch:
    db.add(batch)
    db.flush()
    return batch


def get_profile(db: Session, bank_name: str, headers_hash: str) -> ImportMappingProfile | None:
    """Profile theo tên ngân hàng (không phân biệt hoa thường) + bộ tiêu đề cột."""
    stmt = select(ImportMappingProfile).where(
        func.lower(ImportMappingProfile.bank_name) == bank_name.lower(),
        ImportMappingProfile.headers_hash == headers_hash,
    )
    return db.scalar(stmt.limit(1))


def latest_profile_for_headers(db: Session, headers_hash: str) -> ImportMappingProfile | None:
    """Profile dùng gần nhất cho bộ tiêu đề cột này (bất kể ngân hàng)."""
    stmt = (
        select(ImportMappingProfile)
        .where(ImportMappingProfile.headers_hash == headers_hash)
        .order_by(
            ImportMappingProfile.last_used_at.desc().nulls_last(),
            ImportMappingProfile.updated_at.desc(),
        )
        .limit(1)
    )
    return db.scalar(stmt)


def list_profiles(db: Session, bank_name: str | None = None) -> list[ImportMappingProfile]:
    stmt = select(ImportMappingProfile)
    if bank_name:
        stmt = stmt.where(func.lower(ImportMappingProfile.bank_name) == bank_name.lower())
    stmt = stmt.order_by(
        ImportMappingProfile.last_used_at.desc().nulls_last(),
        ImportMappingProfile.bank_name,
    )
    return list(db.scalars(stmt))


def add_profile(db: Session, profile: ImportMappingProfile) -> ImportMappingProfile:
    db.add(profile)
    db.flush()
    return profile
