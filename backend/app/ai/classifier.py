"""Classifier dùng preference đã học (Phase 3).

- Exact match (pattern đủ cụ thể, mọi token có trong câu) → `ClassificationSuggestion`
  deterministic, không cần LLM cho phần phân loại.
- Không exact → top-5 preference liên quan được đưa vào prompt làm few-shot (`format_few_shot`).

Chỉ đọc preference qua `services`; không ghi DB (hit_count tăng khi user xác nhận giao dịch).
"""

from collections.abc import Iterable

from app.models import ClassificationPreference
from app.schemas.ai import ClassificationSuggestion, TransactionDraft
from app.services import classification_preference_service
from app.services.classification_text import tokenize

PREFERENCE_CONFIDENCE = 0.95

_SPENDING_TYPE_LABELS = {
    "essential": "Thiết yếu",
    "non_essential": "Không thiết yếu",
    "irregular": "Bất thường",
}


def describe(preference: ClassificationPreference) -> str:
    """“giay” → Mua sắm · Thiết yếu"""
    target = preference.category.name
    if preference.spending_type:
        target += f" · {_SPENDING_TYPE_LABELS[preference.spending_type]}"
    return f"“{preference.pattern}” → {target}"


def suggestion_from_preference(preference: ClassificationPreference) -> ClassificationSuggestion:
    return ClassificationSuggestion(
        category_slug=preference.category.slug,
        spending_type=preference.spending_type,
        confidence=PREFERENCE_CONFIDENCE,
        reason=f"Theo sở thích phân loại đã học: {describe(preference)}",
        matched_preference_id=preference.id,
    )


def match_preference(
    text: str,
    preferences: list[ClassificationPreference],
    *,
    direction: str | None = None,
    extra_tokens: Iterable[str] = (),
) -> ClassificationPreference | None:
    """Preference exact-match với câu (và đúng chiều tiền nếu có `direction`)."""
    tokens = set(tokenize(text)) | set(extra_tokens)
    candidates = [p for p in preferences if direction is None or p.category.kind == direction]
    return classification_preference_service.find_exact(candidates, tokens)


def apply_to_draft(
    draft: TransactionDraft, preference: ClassificationPreference
) -> TransactionDraft:
    suggestion = suggestion_from_preference(preference)
    category = preference.category
    return draft.model_copy(
        update={
            "category_slug": category.slug,
            "category_id": category.id,
            "spending_type": (preference.spending_type or category.default_spending_type)
            if category.kind == "expense"
            else None,
            "confidence": max(draft.confidence, suggestion.confidence),
            "reason": suggestion.reason,
            "matched_preference_id": preference.id,
        }
    )


def apply_preferences(
    drafts: list[TransactionDraft], preferences: list[ClassificationPreference], raw_text: str
) -> list[TransactionDraft]:
    """Hậu kiểm draft của model: khoản nào exact-match preference thì phân loại theo preference.

    Khớp theo ghi chú của từng draft; câu chỉ có 1 draft thì dùng thêm token của câu gốc.
    """
    if not preferences:
        return drafts
    extra = tokenize(raw_text) if len(drafts) == 1 else []
    result = []
    for draft in drafts:
        preference = match_preference(
            draft.note, preferences, direction=draft.direction, extra_tokens=extra
        )
        result.append(apply_to_draft(draft, preference) if preference else draft)
    return result


def format_few_shot(preferences: list[ClassificationPreference]) -> str:
    if not preferences:
        return "(chưa có sở thích nào liên quan)"
    return "\n".join(
        f"- từ khoá “{p.pattern}” (ví dụ: “{p.example_text}”) → category_slug `{p.category.slug}`, "
        f"spending_type `{p.spending_type or 'null'}` (đã xác nhận {p.hit_count} lần)"
        for p in preferences
    )
