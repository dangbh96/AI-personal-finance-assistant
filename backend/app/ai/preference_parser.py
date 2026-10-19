"""Parse câu sở thích phân loại ("Tao coi giày là thiết yếu") → `PreferenceDraft` (chưa lưu DB).

User xác nhận draft rồi mới gọi `POST /classification-preferences`.
"""

from functools import cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai import classifier, openai_client
from app.ai.openai_client import OutputValidationError
from app.models import Category
from app.schemas.ai import PreferenceDraft, PreferenceDraftOutput
from app.services import category_service, classification_preference_service
from app.services.classification_text import is_specific, normalize_pattern

PROMPT_FILE = Path(__file__).parent / "prompts" / "classification_preference_parse.v1.md"
TASK = "classification_preference_parse"
LOW_CONFIDENCE = 0.6


@cache
def _prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def build_messages(text: str, categories: list[Category]) -> list[openai_client.Message]:
    rows = "\n".join(
        f"| {c.slug} | {c.name} | {c.kind} | {c.default_spending_type or '—'} |" for c in categories
    )
    system = _prompt_template().replace("{{categories}}", rows)
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _validator(categories_by_slug: dict[str, Category]):
    def validate(output: PreferenceDraftOutput) -> None:
        problems = []
        category = categories_by_slug.get(output.category_slug)
        if category is None:
            problems.append(
                f"category_slug '{output.category_slug}' không có; chọn một trong: "
                + ", ".join(categories_by_slug)
            )
        elif category.kind == "income" and output.spending_type is not None:
            problems.append("danh mục income phải có spending_type = null")
        if not is_specific(normalize_pattern(output.pattern)):
            problems.append(
                f"pattern '{output.pattern}' quá chung; cần từ khoá chỉ loại món, vd 'giày'"
            )
        if problems:
            raise OutputValidationError("; ".join(problems))

    return validate


def parse_preference(db: Session, text: str) -> PreferenceDraft:
    openai_client.ensure_configured()
    text = text.strip()
    categories = category_service.list_categories(db)
    categories_by_slug = {c.slug: c for c in categories}

    output, model = openai_client.structured_completion(
        PreferenceDraftOutput,
        build_messages(text, categories),
        task=TASK,
        model=openai_client.model_fast(),
        validate=_validator(categories_by_slug),
    )

    category = categories_by_slug[output.category_slug]
    spending_type = (
        (output.spending_type or category.default_spending_type)
        if category.kind == "expense"
        else None
    )
    pattern = normalize_pattern(output.pattern)

    warnings = []
    if output.confidence < LOW_CONFIDENCE:
        warnings.append("Mình chưa chắc đây là một sở thích phân loại — bạn kiểm tra lại giúp nhé.")
    existing = classification_preference_service.get_by_pattern(db, pattern)
    if existing is not None and (
        existing.category_id != category.id or existing.spending_type != spending_type
    ):
        warnings.append(
            f"Bạn đã có sở thích {classifier.describe(existing)}; lưu sẽ thay bằng cách mới."
        )

    return PreferenceDraft(
        pattern=pattern,
        category_slug=category.slug,
        category_id=category.id,
        spending_type=spending_type,
        confidence=output.confidence,
        reason=output.reason,
        example_text=text,
        model=model,
        warnings=warnings,
    )
