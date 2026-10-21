"""Classification memory (Phase 3) — deterministic, không gọi AI (ADR-005).

- Tìm preference khớp câu nhập: exact (mọi token của pattern có trong câu, pattern đủ cụ thể) và
  top-N liên quan (có token chung) để làm few-shot.
- Học từ correction: khi user lưu giao dịch có `ai_suggestion` mà đã sửa category/spending_type →
  ghi `classification_feedback` + upsert preference. Không sửa nhưng draft dùng preference → tăng
  `hit_count`.
- Explicit preference ("Tao coi giày là thiết yếu") chỉ lưu khi user xác nhận.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import Category, ClassificationFeedback, ClassificationPreference, Transaction
from app.models.enums import SPENDING_TYPES
from app.repositories import (
    category_repository,
    classification_feedback_repository,
    classification_preference_repository,
)
from app.schemas.classification import PreferenceCreate
from app.services.amount_text import extract_amounts
from app.services.classification_text import (
    extract_keyword,
    is_specific,
    normalize_pattern,
    normalize_text,
    overlap,
    pattern_matches,
)

FEW_SHOT_LIMIT = 5


# ---------- đọc / tìm ----------


def list_preferences(
    db: Session,
    *,
    q: str | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[ClassificationPreference]:
    q = q.strip() if q else None
    return classification_preference_repository.list_preferences(
        db,
        q=q,
        q_pattern=normalize_text(q) if q else None,
        category_id=category_id,
        limit=limit,
    )


def active_preferences(db: Session) -> list[ClassificationPreference]:
    """Preference còn dùng được (danh mục chưa bị ẩn) — đầu vào cho classifier."""
    return classification_preference_repository.list_preferences(db, active_only=True)


def get_preference(db: Session, preference_id: uuid.UUID) -> ClassificationPreference:
    preference = classification_preference_repository.get(db, preference_id)
    if preference is None:
        raise NotFoundError("Không tìm thấy sở thích phân loại", "preference_not_found")
    return preference


def get_by_pattern(db: Session, pattern: str) -> ClassificationPreference | None:
    return classification_preference_repository.get_by_pattern(db, pattern)


def _rank(preference: ClassificationPreference) -> tuple[int, datetime]:
    used = preference.last_used_at or preference.updated_at or preference.created_at
    return preference.hit_count, used or datetime.min.replace(tzinfo=UTC)


def find_exact(
    preferences: list[ClassificationPreference], tokens: set[str]
) -> ClassificationPreference | None:
    """Preference đủ cụ thể có mọi token nằm trong câu; nhiều cái khớp → pattern dài nhất, rồi
    dùng nhiều nhất, rồi mới nhất."""
    candidates = [
        p for p in preferences if is_specific(p.pattern) and pattern_matches(p.pattern, tokens)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (len(p.pattern.split()), *_rank(p)))


def related(
    preferences: list[ClassificationPreference],
    tokens: set[str],
    limit: int = FEW_SHOT_LIMIT,
) -> list[ClassificationPreference]:
    """Tối đa `limit` preference có token chung với câu (để làm few-shot)."""
    scored = [(overlap(p.pattern, tokens), p) for p in preferences]
    scored = [(score, p) for score, p in scored if score > 0]
    scored.sort(key=lambda item: (item[0], *_rank(item[1])), reverse=True)
    return [p for _, p in scored[:limit]]


# ---------- ghi ----------


def _now() -> datetime:
    return datetime.now(UTC)


def _resolve_spending_type(category: Category, spending_type: str | None) -> str | None:
    if category.kind == "income":
        if spending_type is not None:
            raise DomainError(
                "Thu nhập không có loại chi tiêu (spending_type phải null)", "income_spending_type"
            )
        return None
    resolved = spending_type or category.default_spending_type
    if resolved is None:
        raise DomainError("Cần chọn loại chi tiêu cho khoản chi", "spending_type_required")
    return resolved


def _upsert(
    db: Session,
    *,
    pattern: str,
    category: Category,
    spending_type: str | None,
    example_text: str,
    confirmations: int,
) -> ClassificationPreference:
    """Mỗi pattern 1 preference. Đổi cách phân loại → `hit_count` đếm lại từ đầu."""
    preference = classification_preference_repository.get_by_pattern(db, pattern)
    if preference is None:
        preference = ClassificationPreference(
            pattern=pattern,
            example_text=example_text,
            category=category,
            spending_type=spending_type,
            hit_count=confirmations,
            last_used_at=_now() if confirmations else None,
        )
        return classification_preference_repository.add(db, preference)

    unchanged = preference.category_id == category.id and preference.spending_type == spending_type
    preference.category = category
    preference.spending_type = spending_type
    preference.example_text = example_text
    preference.hit_count = (preference.hit_count if unchanged else 0) + confirmations
    if confirmations:
        preference.last_used_at = _now()
    db.flush()
    return preference


def create_preference(db: Session, data: PreferenceCreate) -> ClassificationPreference:
    """Lưu explicit preference user đã xác nhận (trùng pattern → cập nhật)."""
    pattern = normalize_pattern(data.pattern)
    if not is_specific(pattern):
        raise DomainError(
            f"Từ khoá “{data.pattern}” quá chung — bạn chọn từ cụ thể hơn, ví dụ “giày”, "
            "“sửa laptop”.",
            "preference_too_broad",
        )
    category = category_repository.get_by_slug(db, data.category_slug)
    if category is None:
        raise DomainError("Danh mục không tồn tại", "category_not_found")
    if category.is_archived:
        raise DomainError(f"Danh mục '{category.name}' đã bị ẩn", "category_archived")

    preference = _upsert(
        db,
        pattern=pattern,
        category=category,
        spending_type=_resolve_spending_type(category, data.spending_type),
        example_text=data.example_text or data.pattern,
        confirmations=0,
    )
    db.commit()
    db.refresh(preference)
    return preference


def delete_preference(db: Session, preference_id: uuid.UUID) -> None:
    classification_preference_repository.delete(db, get_preference(db, preference_id))
    db.commit()


# ---------- học từ giao dịch đã xác nhận ----------


@dataclass(frozen=True)
class _AiSuggestion:
    category_id: uuid.UUID
    spending_type: str | None
    matched_preference_id: uuid.UUID | None
    note: str | None


def _as_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _parse_ai_suggestion(db: Session, raw: Any) -> _AiSuggestion | None:
    """Đọc phần phân loại trong `transactions.ai_suggestion` (draft gốc AI trả về)."""
    if not isinstance(raw, dict):
        return None
    category = None
    if category_id := _as_uuid(raw.get("category_id")):
        category = category_repository.get(db, category_id)
    if category is None and isinstance(raw.get("category_slug"), str):
        category = category_repository.get_by_slug(db, raw["category_slug"])
    if category is None:
        return None
    spending_type = raw.get("spending_type")
    note = raw.get("note")
    return _AiSuggestion(
        category_id=category.id,
        spending_type=spending_type if spending_type in SPENDING_TYPES else None,
        matched_preference_id=_as_uuid(raw.get("matched_preference_id")),
        note=note if isinstance(note, str) else None,
    )


def _keyword_for(transaction: Transaction, suggestion: _AiSuggestion) -> str | None:
    keyword = extract_keyword(transaction.note) or extract_keyword(suggestion.note)
    raw_input = transaction.raw_input
    # Câu gốc có nhiều khoản tiền thì không biết keyword thuộc khoản nào → không dùng.
    if keyword is None and raw_input and len(extract_amounts(raw_input)) <= 1:
        keyword = extract_keyword(raw_input)
    return keyword


def record_feedback(
    db: Session,
    transaction: Transaction,
    *,
    keyword: str | None = None,
    guess_keyword: bool = True,
) -> ClassificationPreference | None:
    """Gọi sau khi giao dịch đã flush, trước commit. Trả preference vừa học (nếu có).

    - User sửa category/spending_type so với `ai_suggestion` → lưu feedback + upsert preference
      (pattern của preference đã dùng cho draft, nếu không có thì keyword của giao dịch).
    - Không sửa và draft dùng preference → tăng `hit_count` của preference đó.

    Phase 13: `guess_keyword=False` → không đoán keyword từ ghi chú, học theo `keyword` truyền vào
    (hoá đơn học theo tên cửa hàng); `keyword=None` thì chỉ lưu feedback, không học preference mới.
    """
    suggestion = _parse_ai_suggestion(db, transaction.ai_suggestion)
    if suggestion is None:
        return None

    matched = (
        classification_preference_repository.get(db, suggestion.matched_preference_id)
        if suggestion.matched_preference_id
        else None
    )
    corrected = (
        suggestion.category_id != transaction.category_id
        or suggestion.spending_type != transaction.spending_type
    )
    if not corrected:
        if (
            matched is not None
            and matched.category_id == transaction.category_id
            and matched.spending_type == transaction.spending_type
        ):
            matched.hit_count += 1
            matched.last_used_at = _now()
            db.flush()
        return None

    classification_feedback_repository.add(
        db,
        ClassificationFeedback(
            transaction_id=transaction.id,
            ai_category_id=suggestion.category_id,
            ai_spending_type=suggestion.spending_type,
            final_category_id=transaction.category_id,
            final_spending_type=transaction.spending_type,
        ),
    )

    if matched is not None:
        pattern = matched.pattern
    elif guess_keyword:
        pattern = _keyword_for(transaction, suggestion)
    else:
        pattern = normalize_pattern(keyword) if keyword else None
    if not pattern or not is_specific(pattern):
        return None
    return _upsert(
        db,
        pattern=pattern,
        category=transaction.category,
        spending_type=transaction.spending_type,
        example_text=transaction.raw_input or transaction.note or pattern,
        confirmations=1,
    )


__all__ = [
    "FEW_SHOT_LIMIT",
    "active_preferences",
    "create_preference",
    "delete_preference",
    "find_exact",
    "get_by_pattern",
    "get_preference",
    "list_preferences",
    "record_feedback",
    "related",
]
