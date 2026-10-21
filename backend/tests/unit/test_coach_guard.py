"""`services/coach_guard` — response_guard deterministic của Financial Coach (phase-10 § 4.3)."""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.coach import EvidenceItem
from app.services import coach_guard
from app.services.coach_guard import (
    REFUSED_OUT_OF_SCOPE,
    REFUSED_WRITE_REQUEST,
    check_answer,
    classify_request,
)

TODAY = date(2026, 10, 5)
TREND = {
    "months": ["2026-07", "2026-08", "2026-09"],
    "items": [
        {
            "category_name": "Ăn uống",
            "totals_by_month": {"2026-07": 4_000_000, "2026-08": 4_100_000, "2026-09": 4_200_000},
            "latest_total": 4_200_000,
            "delta_vs_previous_pct": 2,
        },
        {
            "category_name": "Mua sắm",
            "totals_by_month": {"2026-07": 1_500_000, "2026-08": 1_000_000, "2026-09": 3_800_000},
            "latest_total": 3_800_000,
            "share_pct": 41.8,
        },
    ],
}
ALLOWED = coach_guard.allowed_numbers([TREND], "Tao nên giảm khoản nào?", TODAY)

VALID = (
    "**Quan sát**\n"
    "- Ăn uống tháng 9/2026: 4.200.000 ₫.\n"
    "- Mua sắm: 3.800.000 ₫ (41,8%), tháng 8 chỉ 1 triệu.\n\n"
    "**Vì sao**\nMua sắm biến động mạnh nhất trong 3 tháng.\n\n"
    "**Bạn có thể cân nhắc**\nNếu bạn muốn, có thể đặt giới hạn cho mua sắm ở "
    "[Ngân sách](/budget/advice?month=2026-09-01)."
)


@pytest.mark.parametrize(
    "question",
    [
        "Mua cổ phiếu nào tuần này?",
        "co phieu nao dang tang",
        "Có nên mua Bitcoin không?",
        "Quyết toán thuế TNCN thế nào?",
        "Nên đầu tư chứng khoán hay gửi tiết kiệm?",
        "Crypto có ổn không",
    ],
)
def test_out_of_scope_questions(question):
    assert classify_request(question) == REFUSED_OUT_OF_SCOPE


@pytest.mark.parametrize(
    "question",
    [
        "Tự giảm budget mua sắm giúp tao",
        "Xoá giao dịch cafe hôm qua giúp tao",
        "Giảm ngân sách ăn uống xuống 3 triệu",
        "Tạo ngân sách tháng sau cho tao",
        "Thêm giao dịch ăn phở 55k hộ mình",
    ],
)
def test_write_requests(question):
    assert classify_request(question) == REFUSED_WRITE_REQUEST


@pytest.mark.parametrize(
    "question",
    [
        "Tao nên giảm khoản nào?",
        "Tháng này khoản nào vượt budget?",
        "Có nên tăng ngân sách ăn uống không?",
        "Tiền thuê nhà tháng này bao nhiêu?",  # "thuê" ≠ "thuế"
        "Giúp tao xem nên giảm khoản nào trong ngân sách",
        "Có khoản bất thường nào không?",
        "Quy mô chi tiêu tháng này so với tháng trước?",
    ],
)
def test_normal_questions(question):
    assert classify_request(question) is None


def test_refusal_answers_pass_guard_and_link_screens():
    out = coach_guard.refusal_answer(REFUSED_OUT_OF_SCOPE, "Mua cổ phiếu nào?")
    assert "không tư vấn đầu tư" in out and check_answer(out, ALLOWED) == []
    write = coach_guard.refusal_answer(REFUSED_WRITE_REQUEST, "Tự giảm budget mua sắm giúp tao")
    assert "[Ngân sách](/budget)" in write and "[Tư vấn ngân sách](/budget/advice)" in write
    assert check_answer(write, ALLOWED) == []
    tx = coach_guard.refusal_answer(REFUSED_WRITE_REQUEST, "Xoá giao dịch cafe giúp tao")
    assert "(/transactions)" in tx


def test_valid_answer_passes():
    assert check_answer(VALID, ALLOWED) == []


def test_banned_phrase_requires_rewrite():
    # Test case 5.
    problems = check_answer(VALID.replace("biến động mạnh nhất", "bạn tiêu quá nhiều"), ALLOWED)
    assert any("bạn tiêu quá nhiều" in p for p in problems)
    for phrase in ("lãng phí", "Bạn phải", "ngay lập tức", "tôi đã điều chỉnh"):
        assert check_answer(f"{VALID}\n{phrase} thôi.", ALLOWED), phrase


def test_invented_number_fails():
    # Test case 6.
    problems = check_answer(VALID.replace("4.200.000", "9.999.999"), ALLOWED)
    assert problems and "9.999.999" in problems[0]
    assert Decimal(9_999_999) not in ALLOWED


def test_numbers_from_keys_question_today_and_small_numbers_are_allowed():
    assert {Decimal(2026), Decimal(9), Decimal(7)} <= ALLOWED
    allowed = coach_guard.allowed_numbers([], "Nếu giảm 20% mua sắm thì sao?", TODAY)
    assert Decimal(20) in allowed and Decimal(5) in allowed
    assert Decimal(13) not in coach_guard.allowed_numbers([], "", date(2026, 10, 1))


def test_ids_in_tool_output_are_not_allowed_numbers():
    allowed = coach_guard.allowed_numbers(
        [{"budget_id": "123e4567-e89b-12d3-a456-426614174000", "amount": 1}], "", TODAY
    )
    assert Decimal(426614174000) not in allowed


def test_data_answer_needs_three_sections_and_condition():
    no_sections = "Ăn uống tháng 9 là 4.200.000 ₫, cao nhất."
    problems = check_answer(no_sections, ALLOWED)
    assert any("Quan sát" in p for p in problems) and any("Vì sao" in p for p in problems)
    assert any("điều kiện" in p for p in problems)


def test_recommendation_without_condition_fails():
    assert check_answer("Bạn nên giảm mua sắm.", ALLOWED)
    assert check_answer("Bạn có thể cân nhắc giảm mua sắm.", ALLOWED) == []
    assert check_answer("Tháng 10/2026 chưa có ngân sách đang theo dõi.", ALLOWED) == []


def test_technical_names_are_rejected():
    problems = check_answer(VALID + "\nTheo latest_total từ get_category_trend.", ALLOWED)
    assert any("latest_total" in p for p in problems)


def test_fallback_answer_passes_guard():
    evidence = [
        EvidenceItem(
            ref="E1",
            tool="t",
            label="Ăn uống",
            period="09/2026",
            metric="Chi tiêu",
            amount=4_200_000,
        ),
        EvidenceItem(
            ref="E2",
            tool="t",
            label="Mua sắm",
            period="09/2026",
            metric="Chênh lệch",
            amount=-1_800_000,
        ),
    ]
    text = coach_guard.fallback_answer(evidence)
    allowed = coach_guard.allowed_numbers([[e.model_dump() for e in evidence]], "", TODAY)
    assert check_answer(text, allowed) == []
    assert "4.200.000 ₫" in text and "-1.800.000 ₫" in text
    empty = coach_guard.fallback_answer([])
    assert check_answer(empty, coach_guard.allowed_numbers([], "", TODAY)) == []


@pytest.mark.parametrize(
    ("question", "title"),
    [
        ("Tao nên giảm khoản nào?", "Nên giảm khoản nào"),
        ("  tháng này khoản nào vượt budget? ", "Tháng này khoản nào vượt budget"),
        ("Mình muốn xem chi tiêu ăn uống ba tháng gần đây có tăng không", None),
        ("???", "Cuộc trò chuyện mới"),
    ],
)
def test_make_title(question, title):
    result = coach_guard.make_title(question)
    if title is None:
        assert result == "Muốn xem chi tiêu ăn uống ba tháng"
    else:
        assert result == title
