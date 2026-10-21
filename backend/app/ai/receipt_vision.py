"""Đọc ảnh hoá đơn bằng model vision (Phase 13) → `ReceiptAnalysis` (chưa lưu DB).

- Model `OPENAI_MODEL_SMART` (mặc định gpt-4o), Structured Output `ReceiptVisionOutput`
  (extraction + đề xuất danh mục chi trong cùng lời gọi), qua `openai_client` (retry, timeout, log).
- Chỉ gửi ảnh + prompt trích xuất + bảng danh mục chi; không gửi lịch sử giao dịch.
- Hậu kiểm: slug thuộc danh mục chi đang dùng, `total` > 0 (sai → model sửa 1 lần).
- Phân loại tái dùng classifier Phase 3: tên cửa hàng exact-match sở thích đã học → theo sở thích.
- Không raise lỗi AI: trả `ReceiptAnalysis(error_code=…)` để `receipt_service` đánh dấu `failed`.
- Không log ảnh / base64 — chỉ receipt id, model, trạng thái (token / latency do `openai_client`).
"""

import base64
import logging
import uuid
from datetime import date
from functools import cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai import classifier, openai_client
from app.ai.openai_client import AIUnavailable, OutputValidationError
from app.models import Category, ClassificationPreference
from app.schemas.ai import ClassificationSuggestion
from app.schemas.receipt import ReceiptAnalysis, ReceiptVisionOutput
from app.services import category_service, classification_preference_service

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent / "prompts" / "receipt_vision_v1.md"
TASK = "receipt_vision"
TIMEOUT_SECONDS = 60.0
IMAGE_DETAIL = "high"


@cache
def _prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def expense_categories(categories: list[Category]) -> list[Category]:
    return [c for c in categories if c.kind == "expense" and not c.is_archived]


def build_messages(
    content: bytes, mime_type: str, categories: list[Category], today: date
) -> list[openai_client.Message]:
    rows = "\n".join(
        f"| {c.slug} | {c.name} | {c.default_spending_type or '—'} |" for c in categories
    )
    system = (
        _prompt_template().replace("{{today}}", today.isoformat()).replace("{{categories}}", rows)
    )
    data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Đọc ảnh hoá đơn này và trả JSON đúng schema."},
                {"type": "image_url", "image_url": {"url": data_url, "detail": IMAGE_DETAIL}},
            ],
        },
    ]


def _validator(expense_slugs: set[str]):
    def validate(output: ReceiptVisionOutput) -> None:
        problems = []
        if output.category_slug not in expense_slugs:
            problems.append(
                f"category_slug '{output.category_slug}' không có; slug hợp lệ: "
                + ", ".join(sorted(expense_slugs))
            )
        if output.total is not None and output.total <= 0:
            problems.append("total phải là số nguyên đồng > 0, hoặc null nếu không đọc được")
        if any(item.amount is not None and item.amount < 0 for item in output.items):
            problems.append("amount của dòng hàng phải ≥ 0 hoặc null")
        if problems:
            raise OutputValidationError("; ".join(problems))

    return validate


def classify(
    output: ReceiptVisionOutput, preferences: list[ClassificationPreference]
) -> ClassificationSuggestion:
    """Tên cửa hàng exact-match sở thích phân loại đã học → theo sở thích; không thì theo model."""
    if output.merchant:
        preference = classifier.match_preference(output.merchant, preferences, direction="expense")
        if preference is not None:
            return classifier.suggestion_from_preference(preference)
    return ClassificationSuggestion(
        category_slug=output.category_slug,
        spending_type=output.spending_type,
        confidence=output.confidence,
        reason=output.classification_reason,
    )


def analyze(
    db: Session,
    content: bytes,
    mime_type: str,
    *,
    receipt_id: uuid.UUID | None = None,
    today: date | None = None,
) -> ReceiptAnalysis:
    """Gọi model vision cho một ảnh (JPEG / PNG / WEBP) và phân loại kết quả."""
    today = today or date.today()
    try:
        openai_client.ensure_configured()
        categories = expense_categories(category_service.list_categories(db))
        output, model = openai_client.structured_completion(
            ReceiptVisionOutput,
            build_messages(content, mime_type, categories, today),
            task=TASK,
            model=openai_client.model_smart(),
            timeout=TIMEOUT_SECONDS,
            validate=_validator({c.slug for c in categories}),
        )
    except AIUnavailable as exc:
        logger.warning("receipt_vision receipt=%s error=%s", receipt_id, exc.code)
        return ReceiptAnalysis(error_code=exc.code, error_message=exc.detail)

    suggestion = classify(output, classification_preference_service.active_preferences(db))
    logger.info(
        "receipt_vision receipt=%s model=%s confidence=%.2f has_total=%s items=%d",
        receipt_id,
        model,
        output.confidence,
        output.total is not None,
        len(output.items),
    )
    return ReceiptAnalysis(output=output, suggestion=suggestion, model=model)
