import pytest
from pydantic import ValidationError

from app.schemas.ai import TransactionDraftOutput, TransactionParseOutput, TransactionParseRequest

BASE = {
    "direction": "expense",
    "amount": 55_000,
    "occurred_on": "2026-10-07",
    "note": "Ăn phở",
    "category_slug": "food",
    "spending_type": "essential",
    "confidence": 0.9,
    "reason": "Bữa ăn chính",
}


def test_valid_expense_draft():
    draft = TransactionDraftOutput.model_validate(BASE)
    assert draft.amount == 55_000


@pytest.mark.parametrize(
    "patch",
    [
        {"amount": 0},
        {"amount": -1000},
        {"amount": 55_000.5},
        {"direction": "transfer"},
        {"spending_type": "luxury"},
        {"confidence": 1.5},
        {"direction": "income", "spending_type": "essential"},
        {"spending_type": None},
    ],
)
def test_invalid_draft_rejected(patch):
    with pytest.raises(ValidationError):
        TransactionDraftOutput.model_validate({**BASE, **patch})


def test_income_draft_without_spending_type():
    draft = TransactionDraftOutput.model_validate(
        {**BASE, "direction": "income", "category_slug": "salary", "spending_type": None}
    )
    assert draft.spending_type is None


def test_parse_output_needs_one_to_ten_transactions():
    with pytest.raises(ValidationError):
        TransactionParseOutput.model_validate({"transactions": [], "warnings": []})
    with pytest.raises(ValidationError):
        TransactionParseOutput.model_validate({"transactions": [BASE] * 11, "warnings": []})


@pytest.mark.parametrize("text", ["", "   ", "x" * 501])
def test_parse_request_text_length(text):
    with pytest.raises(ValidationError):
        TransactionParseRequest(text=text)


def test_parse_request_rejects_unknown_timezone():
    with pytest.raises(ValidationError):
        TransactionParseRequest(text="ăn phở 55k", timezone="Mars/Olympus")


def test_parse_request_defaults():
    req = TransactionParseRequest(text="  ăn phở 55k  ")
    assert req.text == "ăn phở 55k"
    assert req.today is None
    assert req.timezone == "Asia/Ho_Chi_Minh"
