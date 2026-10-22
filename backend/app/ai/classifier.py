"""Classifier dùng preference đã học (Phase 3) + phân loại hàng loạt khi import sao kê (Phase 14).

- Exact match (pattern đủ cụ thể, mọi token có trong câu) → `ClassificationSuggestion`
  deterministic, không cần LLM cho phần phân loại.
- Không exact → top-5 preference liên quan được đưa vào prompt làm few-shot (`format_few_shot`).
- Import (`classify_batch_import`): dòng exact-match preference dùng luôn (không gửi model); các
  dòng còn lại gom 20 dòng / request gửi `OPENAI_MODEL_FAST`. Chỉ trả đề xuất, không ghi DB.

Chỉ đọc preference qua `services`; không ghi DB (hit_count tăng khi user xác nhận giao dịch).
"""

import json
import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai import openai_client
from app.ai.openai_client import AIUnavailable, OutputValidationError
from app.models import Category, ClassificationPreference
from app.schemas.ai import ClassificationSuggestion, TransactionDraft
from app.schemas.imports import (
    ImportClassification,
    ImportClassificationOutput,
    ImportClassifyItem,
    SuggestionSource,
)
from app.services import category_service, classification_preference_service
from app.services.classification_text import tokenize

logger = logging.getLogger(__name__)

PREFERENCE_CONFIDENCE = 0.95
IMPORT_BATCH_SIZE = 20
IMPORT_MAX_AI_ITEMS = 300
IMPORT_MAX_PARALLEL = 4
IMPORT_TASK = "import_classify"
IMPORT_TIMEOUT_SECONDS = 45.0
IMPORT_PROMPT_FILE = Path(__file__).parent / "prompts" / "import_classification.v1.md"

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


# ---------- phân loại hàng loạt khi import sao kê (Phase 14) ----------


@cache
def _import_prompt_template() -> str:
    return IMPORT_PROMPT_FILE.read_text(encoding="utf-8")


def build_import_messages(
    items: list[ImportClassifyItem],
    categories: list[Category],
    preferences: list[ClassificationPreference],
) -> list[openai_client.Message]:
    """System prompt (bảng danh mục + sở thích liên quan) + user message JSON ≤ 20 dòng."""
    rows = "\n".join(
        f"| {c.slug} | {c.name} | {'thu nhập' if c.kind == 'income' else 'chi tiêu'} | "
        f"{c.default_spending_type or '—'} |"
        for c in categories
    )
    tokens: set[str] = set()
    for item in items:
        tokens.update(tokenize(item.note))
    related = classification_preference_service.related(preferences, tokens)
    system = (
        _import_prompt_template()
        .replace("{{categories}}", rows)
        .replace("{{preferences}}", format_few_shot(related))
    )
    payload = [
        {
            "row_index": item.row_index,
            "note": item.note,
            "amount": item.amount,
            "direction": item.direction,
            "occurred_on": item.occurred_on.isoformat(),
        }
        for item in items
    ]
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": "Phân loại các dòng sao kê sau, trả JSON đúng schema:\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]


def _import_validator(items: list[ImportClassifyItem], categories: list[Category]):
    expected = {item.row_index: item.direction for item in items}
    kinds = {c.slug: c.kind for c in categories}

    def validate(output: ImportClassificationOutput) -> None:
        problems = []
        returned = [item.row_index for item in output.items]
        missing = sorted(set(expected) - set(returned))
        extra = sorted(set(returned) - set(expected))
        repeated = sorted({i for i in returned if returned.count(i) > 1})
        if missing:
            problems.append(f"thiếu row_index {missing}")
        if extra:
            problems.append(f"row_index không được gửi {extra}")
        if repeated:
            problems.append(f"row_index lặp {repeated}")
        for item in output.items:
            direction = expected.get(item.row_index)
            if direction is None:
                continue
            kind = kinds.get(item.category_slug)
            if kind is None:
                problems.append(f"row_index {item.row_index}: slug '{item.category_slug}' không có")
            elif kind != direction:
                problems.append(
                    f"row_index {item.row_index}: '{item.category_slug}' là danh mục "
                    f"{kind}, dòng là {direction}"
                )
            if direction == "income" and item.spending_type is not None:
                problems.append(f"row_index {item.row_index}: income phải có spending_type null")
            if direction == "expense" and item.spending_type is None:
                problems.append(f"row_index {item.row_index}: expense cần spending_type")
        if problems:
            raise OutputValidationError("; ".join(problems))

    return validate


def _chunks[T](items: list[T], size: int) -> list[list[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def classify_batch_import(db: Session, items: list[ImportClassifyItem]) -> ImportClassification:
    """Đề xuất danh mục / loại chi tiêu cho các dòng sao kê — không ghi DB, không raise lỗi AI.

    1. Dòng exact-match sở thích đã học (Phase 3) → theo sở thích, **không** gửi model.
    2. Dòng còn lại gộp theo (nội dung chuẩn hoá, chiều) rồi gửi model 20 dòng / request
       (`OPENAI_MODEL_FAST`, song song tối đa 4), tối đa 300 nội dung khác nhau mỗi lần.
    3. AI lỗi / chưa cấu hình → dòng đó không có đề xuất (service dùng `other`, confidence 0).
    """
    preferences = classification_preference_service.active_preferences(db)
    suggestions: dict[int, ClassificationSuggestion] = {}
    sources: dict[int, SuggestionSource] = {}
    groups: dict[tuple[str, str], list[ImportClassifyItem]] = {}
    for item in items:
        preference = match_preference(item.note, preferences, direction=item.direction)
        if preference is not None:
            suggestions[item.row_index] = suggestion_from_preference(preference)
            sources[item.row_index] = "preference"
            continue
        key = (" ".join(item.note.lower().split()), item.direction)
        groups.setdefault(key, []).append(item)

    result = ImportClassification(suggestions=suggestions, sources=sources)
    if not groups:
        return result
    try:
        openai_client.ensure_configured()
    except AIUnavailable as exc:
        result.error_code, result.error_message = exc.code, exc.detail
        return result

    representatives = [group[0] for group in groups.values()]
    capped = representatives[:IMPORT_MAX_AI_ITEMS]
    categories = category_service.list_categories(db)
    model = openai_client.model_fast()
    prepared = [
        (chunk, build_import_messages(chunk, categories, preferences))
        for chunk in _chunks(capped, IMPORT_BATCH_SIZE)
    ]

    def run(job: tuple[list[ImportClassifyItem], list[openai_client.Message]]):
        chunk, messages = job
        try:
            return openai_client.structured_completion(
                ImportClassificationOutput,
                messages,
                task=IMPORT_TASK,
                model=model,
                timeout=IMPORT_TIMEOUT_SECONDS,
                validate=_import_validator(chunk, categories),
            )
        except AIUnavailable as exc:
            return exc

    if len(prepared) == 1:
        outputs = [run(prepared[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(IMPORT_MAX_PARALLEL, len(prepared))) as pool:
            outputs = list(pool.map(run, prepared))

    by_representative: dict[int, ClassificationSuggestion] = {}
    for outcome in outputs:
        if isinstance(outcome, AIUnavailable):
            if result.error_code is None:
                result.error_code, result.error_message = outcome.code, outcome.detail
            continue
        output, used_model = outcome
        result.model = used_model
        for item in output.items:
            by_representative[item.row_index] = ClassificationSuggestion(
                category_slug=item.category_slug,
                spending_type=item.spending_type,
                confidence=item.confidence,
                reason=item.reason,
            )
    for group in groups.values():
        suggestion = by_representative.get(group[0].row_index)
        if suggestion is None:
            continue
        for item in group:
            suggestions[item.row_index] = suggestion
            sources[item.row_index] = "ai"
    if len(representatives) > IMPORT_MAX_AI_ITEMS and result.error_code is None:
        result.error_code = "AI_ROW_LIMIT"
        result.error_message = (
            f"Chỉ phân loại tự động {IMPORT_MAX_AI_ITEMS} nội dung khác nhau mỗi lần import."
        )
    result.llm_requests = len(prepared)
    result.suggestions, result.sources = suggestions, sources
    logger.info(
        "import_classify items=%d preference=%d groups=%d requests=%d error=%s",
        len(items),
        sum(1 for s in sources.values() if s == "preference"),
        len(groups),
        len(prepared),
        result.error_code,
    )
    return result
