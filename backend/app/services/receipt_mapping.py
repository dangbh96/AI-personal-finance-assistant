"""Map extraction hoá đơn → draft giao dịch (Phase 13) — hàm thuần, deterministic, không AI.

- `assess_extraction`: đủ điều kiện tạo draft hoàn chỉnh khi có `total` > 0, tiền VND và
  `confidence` ≥ 0.6; không thì receipt `failed` + form nhập tay điền sẵn.
- `build_draft` / `build_manual_prefill`: `direction='expense'`, `amount=total`,
  `occurred_on = ngày trên hoá đơn hoặc hôm nay`, `note = "{merchant} - hoá đơn"`.
- `extraction_warnings`: ngày tương lai / quá cũ / không đọc được, tổng dòng hàng ≠ tổng thanh toán.
"""

from dataclasses import dataclass
from datetime import date

from app.core.text import strip_accents
from app.models import Category
from app.schemas.ai import ClassificationSuggestion, TransactionDraft
from app.schemas.common import MAX_AMOUNT
from app.schemas.receipt import ReceiptExtraction, ReceiptManualPrefill
from app.services.money import format_vnd

MIN_DRAFT_CONFIDENCE = 0.6
MAX_PAST_DAYS = 366
SUPPORTED_CURRENCY = "VND"
NOTE_SUFFIX = "hoá đơn"
MAX_NOTE_LENGTH = 500
MAX_MERCHANT_PATTERN_TOKENS = 5

_VND_ALIASES = frozenset({"", "VND", "VNĐ", "Đ", "D", "₫", "DONG", "VIETNAM DONG", "VN DONG"})


@dataclass(frozen=True)
class Assessment:
    usable: bool
    error_code: str | None = None
    error_message: str | None = None


def normalize_currency(currency: str | None) -> str:
    """ "VNĐ", "đ", "₫", "" → "VND"; mã khác giữ nguyên (viết hoa)."""
    value = (currency or "").strip().upper()
    if value in _VND_ALIASES or strip_accents(value) in _VND_ALIASES:
        return SUPPORTED_CURRENCY
    return value


def assess_extraction(extraction: ReceiptExtraction) -> Assessment:
    if extraction.total is None:
        if extraction.unreadable_reason:
            return Assessment(
                False,
                "unreadable",
                f"Không đọc được hoá đơn: {extraction.unreadable_reason}",
            )
        return Assessment(False, "total_missing", "Không đọc được tổng tiền trên hoá đơn.")
    if extraction.total <= 0 or extraction.total > MAX_AMOUNT:
        return Assessment(False, "invalid_total", "Tổng tiền đọc được không hợp lệ.")
    currency = normalize_currency(extraction.currency)
    if currency != SUPPORTED_CURRENCY:
        return Assessment(
            False,
            "unsupported_currency",
            f"Hoá đơn dùng tiền {currency} — app hiện chỉ hỗ trợ VND, bạn nhập tay số tiền đã "
            "quy đổi giúp nhé.",
        )
    if extraction.confidence < MIN_DRAFT_CONFIDENCE:
        reason = f" ({extraction.unreadable_reason})" if extraction.unreadable_reason else ""
        return Assessment(
            False,
            "low_confidence",
            f"AI chưa đọc chắc chắn hoá đơn này{reason} — bạn kiểm tra và nhập tay giúp nhé.",
        )
    return Assessment(True)


def draft_note(merchant: str | None) -> str:
    merchant = (merchant or "").strip()
    note = f"{merchant} - {NOTE_SUFFIX}" if merchant else NOTE_SUFFIX.capitalize()
    return note[:MAX_NOTE_LENGTH]


def resolve_occurred_on(receipt_date: date | None, today: date) -> date:
    return receipt_date or today


def merchant_pattern(merchant: str | None) -> str | None:
    """Từ khoá học phân loại theo cửa hàng (Phase 3 chuẩn hoá lại), tối đa 5 từ."""
    if not merchant or not merchant.strip():
        return None
    return " ".join(merchant.split()[:MAX_MERCHANT_PATTERN_TOKENS])


def resolve_spending_type(suggested: str | None, category: Category) -> str | None:
    return suggested or category.default_spending_type


def build_draft(
    extraction: ReceiptExtraction,
    category: Category,
    suggestion: ClassificationSuggestion,
    today: date,
) -> TransactionDraft:
    """Chỉ gọi khi `assess_extraction(...).usable` (có `total` > 0)."""
    if extraction.total is None:
        raise ValueError("extraction thiếu total")
    return TransactionDraft(
        direction="expense",
        amount=extraction.total,
        occurred_on=resolve_occurred_on(extraction.date, today),
        note=draft_note(extraction.merchant),
        category_slug=category.slug,
        category_id=category.id,
        spending_type=resolve_spending_type(suggestion.spending_type, category),
        confidence=extraction.confidence,
        reason=suggestion.reason[:500],
        matched_preference_id=suggestion.matched_preference_id,
    )


def build_manual_prefill(
    extraction: ReceiptExtraction | None,
    category: Category | None,
    suggestion: ClassificationSuggestion | None,
    today: date,
) -> ReceiptManualPrefill:
    """Form nhập tay điền sẵn phần đoán được (kể cả khi AI lỗi: chỉ có ngày hôm nay)."""
    amount = None
    if (
        extraction is not None
        and extraction.total is not None
        and 0 < extraction.total <= MAX_AMOUNT
        and normalize_currency(extraction.currency) == SUPPORTED_CURRENCY
    ):
        amount = extraction.total
    spending_type = None
    if category is not None:
        suggested = suggestion.spending_type if suggestion else None
        spending_type = resolve_spending_type(suggested, category)
    return ReceiptManualPrefill(
        direction="expense",
        amount=amount,
        occurred_on=resolve_occurred_on(extraction.date if extraction else None, today),
        note=draft_note(extraction.merchant if extraction else None),
        category_id=category.id if category else None,
        category_slug=category.slug if category else None,
        spending_type=spending_type,
    )


def _fmt_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def extraction_warnings(extraction: ReceiptExtraction, today: date) -> list[str]:
    warnings: list[str] = []
    if extraction.merchant is None or not extraction.merchant.strip():
        warnings.append("Không đọc được tên cửa hàng — bạn bổ sung ghi chú giúp nhé.")
    if extraction.date is None:
        warnings.append("Không đọc được ngày trên hoá đơn — tạm dùng ngày hôm nay.")
    elif extraction.date > today:
        warnings.append(
            f"Ngày trên hoá đơn ({_fmt_date(extraction.date)}) ở tương lai — "
            "bạn kiểm tra lại ngày giúp nhé."
        )
    elif (today - extraction.date).days > MAX_PAST_DAYS:
        warnings.append(
            f"Ngày trên hoá đơn ({_fmt_date(extraction.date)}) cách đây hơn một năm — "
            "bạn kiểm tra lại ngày giúp nhé."
        )
    amounts = [item.amount for item in extraction.items]
    if (
        extraction.total is not None
        and amounts
        and all(a is not None for a in amounts)
        and sum(a for a in amounts if a is not None) != extraction.total
    ):
        items_total = sum(a for a in amounts if a is not None)
        warnings.append(
            f"Tổng các dòng hàng ({format_vnd(items_total)}) khác tổng thanh toán "
            f"({format_vnd(extraction.total)}) — có thể do VAT, phí dịch vụ hoặc giảm giá; "
            "draft dùng tổng thanh toán."
        )
    return warnings
