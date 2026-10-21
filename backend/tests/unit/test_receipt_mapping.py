"""Map extraction hoá đơn → draft (Phase 13): hàm thuần, không DB, không AI."""

import uuid
from datetime import date

import pytest

from app.models import Category
from app.schemas.ai import ClassificationSuggestion
from app.schemas.receipt import ReceiptExtraction, ReceiptItem
from app.services import receipt_mapping

TODAY = date(2026, 10, 22)


def food() -> Category:
    return Category(
        id=uuid.uuid4(),
        name="Ăn uống",
        slug="food",
        kind="expense",
        default_spending_type="essential",
        is_archived=False,
    )


def extraction(**overrides) -> ReceiptExtraction:
    data = {
        "merchant": "Co.opmart",
        "date": date(2026, 10, 5),
        "total": 352_000,
        "currency": "VND",
        "items": [
            ReceiptItem(name="Gạo ST25 5kg", qty=1, amount=185_000),
            ReceiptItem(name="Sữa tươi 1L", qty=2, amount=64_000),
            ReceiptItem(name="Rau cải", qty=2, amount=103_000),
        ],
        "confidence": 0.93,
        "unreadable_reason": None,
    }
    data.update(overrides)
    return ReceiptExtraction(**data)


def suggestion(**overrides) -> ClassificationSuggestion:
    data = {
        "category_slug": "food",
        "spending_type": "essential",
        "confidence": 0.9,
        "reason": "Siêu thị bán thực phẩm",
    }
    data.update(overrides)
    return ClassificationSuggestion(**data)


def test_case_4_coopmart_draft():
    """Test case 4: merchant Co.opmart, 2026-10-05, total 352.000, 3 dòng hàng."""
    ex = extraction()
    assert receipt_mapping.assess_extraction(ex).usable
    category = food()
    draft = receipt_mapping.build_draft(ex, category, suggestion(), TODAY)
    assert draft.amount == 352_000
    assert draft.occurred_on == date(2026, 10, 5)
    assert draft.direction == "expense"
    assert "Co.opmart" in draft.note
    assert draft.note == "Co.opmart - hoá đơn"
    assert draft.category_id == category.id
    assert draft.category_slug == "food"
    assert draft.spending_type == "essential"
    assert draft.confidence == 0.93
    assert draft.matched_preference_id is None
    assert receipt_mapping.extraction_warnings(ex, TODAY) == []


def test_case_5_low_confidence_without_total_is_not_usable():
    """Test case 5: confidence 0.42, total null, unreadable_reason "blurry" → failed."""
    ex = extraction(total=None, confidence=0.42, unreadable_reason="blurry", items=[])
    assessment = receipt_mapping.assess_extraction(ex)
    assert not assessment.usable
    assert assessment.error_code == "unreadable"
    assert "blurry" in assessment.error_message
    prefill = receipt_mapping.build_manual_prefill(ex, food(), suggestion(), TODAY)
    assert prefill.amount is None
    assert prefill.occurred_on == date(2026, 10, 5)
    assert prefill.note == "Co.opmart - hoá đơn"
    assert prefill.category_slug == "food"
    assert prefill.direction == "expense"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"total": None}, "total_missing"),
        ({"total": 0}, "invalid_total"),
        ({"total": -5000}, "invalid_total"),
        ({"total": 10**16}, "invalid_total"),
        ({"currency": "USD", "total": 25}, "unsupported_currency"),
        ({"confidence": 0.59}, "low_confidence"),
    ],
)
def test_unusable_extractions(overrides, code):
    assessment = receipt_mapping.assess_extraction(extraction(**overrides))
    assert not assessment.usable
    assert assessment.error_code == code
    assert assessment.error_message


def test_confidence_threshold_is_inclusive():
    assert receipt_mapping.assess_extraction(extraction(confidence=0.6)).usable


@pytest.mark.parametrize("currency", ["VND", "vnd", "VNĐ", "đ", "₫", "", " dong "])
def test_vnd_aliases(currency):
    assert receipt_mapping.normalize_currency(currency) == "VND"
    assert receipt_mapping.assess_extraction(extraction(currency=currency)).usable


def test_low_confidence_prefill_keeps_total():
    ex = extraction(confidence=0.5)
    prefill = receipt_mapping.build_manual_prefill(ex, food(), suggestion(), TODAY)
    assert prefill.amount == 352_000


def test_foreign_currency_prefill_drops_amount():
    ex = extraction(currency="USD", total=25)
    prefill = receipt_mapping.build_manual_prefill(ex, food(), suggestion(), TODAY)
    assert prefill.amount is None


def test_prefill_when_ai_failed():
    prefill = receipt_mapping.build_manual_prefill(None, None, None, TODAY)
    assert prefill.amount is None
    assert prefill.occurred_on == TODAY
    assert prefill.note == "Hoá đơn"
    assert prefill.category_id is None
    assert prefill.spending_type is None


def test_missing_date_uses_today_with_warning():
    ex = extraction(date=None)
    draft = receipt_mapping.build_draft(ex, food(), suggestion(), TODAY)
    assert draft.occurred_on == TODAY
    assert any("ngày hôm nay" in w for w in receipt_mapping.extraction_warnings(ex, TODAY))


def test_missing_merchant_note_and_warning():
    ex = extraction(merchant=None)
    draft = receipt_mapping.build_draft(ex, food(), suggestion(), TODAY)
    assert draft.note == "Hoá đơn"
    assert any("tên cửa hàng" in w for w in receipt_mapping.extraction_warnings(ex, TODAY))


def test_future_and_old_dates_warn():
    future = receipt_mapping.extraction_warnings(extraction(date=date(2026, 11, 2)), TODAY)
    assert any("02/11/2026" in w and "tương lai" in w for w in future)
    old = receipt_mapping.extraction_warnings(extraction(date=date(2025, 10, 1)), TODAY)
    assert any("hơn một năm" in w for w in old)


def test_items_total_mismatch_warning():
    ex = extraction(
        total=748_440,
        items=[
            ReceiptItem(name="Lẩu thái", qty=1, amount=320_000),
            ReceiptItem(name="Gà nướng", qty=1, amount=340_000),
        ],
    )
    warnings = receipt_mapping.extraction_warnings(ex, TODAY)
    assert any("660.000 ₫" in w and "748.440 ₫" in w for w in warnings)


def test_no_mismatch_warning_when_some_item_amount_unknown():
    ex = extraction(items=[ReceiptItem(name="Gạo", qty=None, amount=None)])
    assert receipt_mapping.extraction_warnings(ex, TODAY) == []


def test_spending_type_falls_back_to_category_default():
    draft = receipt_mapping.build_draft(extraction(), food(), suggestion(spending_type=None), TODAY)
    assert draft.spending_type == "essential"


def test_suggested_spending_type_wins():
    draft = receipt_mapping.build_draft(
        extraction(), food(), suggestion(spending_type="non_essential"), TODAY
    )
    assert draft.spending_type == "non_essential"


def test_preference_id_carried_to_draft():
    pref_id = uuid.uuid4()
    draft = receipt_mapping.build_draft(
        extraction(), food(), suggestion(matched_preference_id=pref_id), TODAY
    )
    assert draft.matched_preference_id == pref_id


@pytest.mark.parametrize(
    ("merchant", "expected"),
    [
        ("Co.opmart", "Co.opmart"),
        ("  ", None),
        (None, None),
        ("Nhà hàng Phố Cổ Hà Nội chi nhánh 2", "Nhà hàng Phố Cổ Hà"),
    ],
)
def test_merchant_pattern(merchant, expected):
    assert receipt_mapping.merchant_pattern(merchant) == expected
