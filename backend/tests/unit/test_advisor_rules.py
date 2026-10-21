"""Decision tree Budget advisor (phase-08 § 6, budget-adjustment.md § 1) — hàm thuần, không DB/AI.

CV dùng population std (chia n) — xem `advisor_rules.cv_squared`.
"""

import uuid
from datetime import date
from fractions import Fraction

import pytest

from app.schemas.budget_advice import AdvisorSettings, BudgetAdviceExplanation
from app.services import advice_narrative, advisor_rules
from app.services.advisor_rules import AdviceInput, MonthActual, ScopeTransaction, Thresholds

OCT = date(2026, 10, 1)
MONTHS = (date(2026, 8, 1), date(2026, 9, 1), OCT)


def _tx(amount: int, note: str = "Chi tiêu", spending_type: str = "essential", day: int = 10):
    return ScopeTransaction(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"tx/{note}/{amount}/{day}"),
        occurred_on=date(2026, 10, day),
        note=note,
        amount=amount,
        category_name="Danh mục",
        spending_type=spending_type,
    )


def _split(total: int, piece: int, note: str = "Chi tiêu") -> list[ScopeTransaction]:
    """Chia `total` thành nhiều giao dịch nhỏ (≤ piece) — không giao dịch nào nổi trội."""
    count, rest = divmod(total, piece)
    items = [_tx(piece, note, day=1 + i % 28) for i in range(count)]
    if rest:
        items.append(_tx(rest, note, day=28))
    return items


def _input(
    planned: int,
    history: list[int],
    *,
    transactions: list[ScopeTransaction] | None = None,
    comfort_high: int | None = None,
    label: str = "Ăn uống",
    empty_months: int = 0,
) -> AdviceInput:
    """`history`: thực chi các tháng gần nhất (cuối = tháng 10). `empty_months` tháng đầu không có
    giao dịch nào."""
    months = MONTHS[-len(history) :]
    actual = history[-1]
    return AdviceInput(
        label=label,
        group="essential",
        category_slug="food",
        month=OCT,
        as_of=date(2026, 10, 31),
        month_complete=True,
        planned=planned,
        actual=actual,
        comfort_high=comfort_high,
        transactions=transactions if transactions is not None else _split(actual, 150_000),
        history=[
            MonthActual(m, v, 0 if i < empty_months else max(1, v // 150_000))
            for i, (m, v) in enumerate(zip(months, history, strict=True))
        ],
    )


# ---------- test case chuẩn (phase-08 § 6) ----------


def test_case_1_food_stable_overspend_adjust_budget():
    result = advisor_rules.evaluate(_input(4_000_000, [4_400_000, 4_600_000, 4_500_000]))
    e = result.evidence
    assert result.verdict == "adjust_budget"
    assert e.rule == "stable_overspend"
    assert e.proposed_planned_amount == 4_500_000
    assert [h.actual for h in e.history_actuals] == [4_400_000, 4_600_000, 4_500_000]
    assert [h.month for h in e.history_actuals] == list(MONTHS)
    assert e.all_over_planned is True
    # population std = sqrt(2·100.000² / 3) ≈ 81.650 → CV ≈ 1,81%
    assert (e.cv, e.cv_pct) == (0.0181, 1.8)
    assert (e.over_amount, e.variance, e.history_median) == (500_000, 500_000, 4_500_000)
    assert e.one_off_transaction is None


def test_case_2_shopping_laptop_irregular_is_one_off():
    transactions = [
        _tx(6_500_000, "Laptop", "irregular", day=12),
        *_split(1_500_000, 500_000, "Quần áo"),
    ]
    result = advisor_rules.evaluate(
        _input(2_000_000, [8_000_000], transactions=transactions, label="Mua sắm")
    )
    e = result.evidence
    assert result.verdict == "one_off"
    assert e.rule == "one_off_irregular"
    assert e.proposed_planned_amount is None
    assert e.one_off_transaction is not None
    assert (e.one_off_transaction.note, e.one_off_transaction.amount) == ("Laptop", 6_500_000)
    assert e.irregular_transaction == e.one_off_transaction
    assert (e.over_amount, e.irregular_total) == (6_000_000, 6_500_000)
    # Laptop lớn hơn cả phần vượt → tỉ lệ kẹp ở 1 (như top contributor Phase 5).
    assert (e.irregular_share, e.single_transaction_share) == (1.0, 1.0)


def test_case_3_entertainment_unstable_history_adjust_behavior():
    result = advisor_rules.evaluate(
        _input(
            1_000_000,
            [800_000, 1_600_000, 1_400_000],
            transactions=_split(1_400_000, 200_000, "Xem phim"),
            label="Giải trí",
        )
    )
    e = result.evidence
    assert result.verdict == "adjust_behavior"
    assert e.rule == "unstable_overspend"
    assert e.all_over_planned is False
    assert e.cv_pct == 26.8
    assert e.proposed_planned_amount is None


def test_case_4_transport_under_plan_on_track():
    result = advisor_rules.evaluate(_input(1_000_000, [700_000], label="Đi lại"))
    assert result.verdict == "on_track"
    assert result.evidence.rule == "within_plan"
    assert result.evidence.over_amount == 0
    assert result.evidence.single_transaction_share is None


def test_case_5_insufficient_history_adjust_behavior():
    result = advisor_rules.evaluate(_input(4_000_000, [0, 4_400_000, 4_300_000], empty_months=1))
    e = result.evidence
    assert result.verdict == "adjust_behavior"
    assert e.rule == "insufficient_history"
    assert (e.history_months, e.min_history_months) == (2, 3)
    assert [h.has_data for h in e.history_actuals] == [False, True, True]


def test_case_5_history_shorter_than_window():
    result = advisor_rules.evaluate(_input(4_000_000, [4_400_000, 4_300_000]))
    assert result.verdict == "adjust_behavior"
    assert result.evidence.history_months == 2
    assert result.evidence.cv is None and result.evidence.history_median is None


def test_case_6_comfort_high_takes_priority_over_planned():
    result = advisor_rules.evaluate(
        _input(4_000_000, [4_400_000, 4_600_000, 4_300_000], comfort_high=4_500_000)
    )
    e = result.evidence
    assert result.verdict == "on_track"
    assert (e.comfort_high_used, e.threshold_amount, e.over_amount) == (True, 4_500_000, 0)
    assert e.variance == 300_000


# ---------- từng nhánh / biên ----------


def test_actual_equal_planned_is_on_track():
    assert advisor_rules.evaluate(_input(4_000_000, [4_000_000])).verdict == "on_track"


def test_single_regular_transaction_at_60_percent_is_one_off():
    # Vượt 500.000; giao dịch 300.000 = đúng 60% phần vượt → one_off (>=).
    transactions = [_tx(300_000, "Tiệc sinh nhật", "non_essential"), *_split(4_200_000, 150_000)]
    result = advisor_rules.evaluate(
        _input(4_000_000, [4_400_000, 4_600_000, 4_500_000], transactions=transactions)
    )
    assert result.verdict == "one_off"
    assert result.evidence.rule == "one_off_single_transaction"
    assert result.evidence.single_transaction_share_pct == 60.0
    assert result.evidence.one_off_transaction.note == "Tiệc sinh nhật"


def test_single_transaction_just_below_threshold_is_not_one_off():
    transactions = [_tx(299_999, "Tiệc"), *_split(4_200_001, 150_000)]
    result = advisor_rules.evaluate(
        _input(4_000_000, [4_400_000, 4_600_000, 4_500_000], transactions=transactions)
    )
    assert result.verdict == "adjust_budget"


def test_small_irregular_transactions_do_not_make_one_off():
    # Có giao dịch bất thường nhưng chỉ 100.000 / 500.000 vượt = 20% → đi tiếp decision tree.
    transactions = [_tx(100_000, "Thuốc", "irregular"), *_split(4_400_000, 150_000)]
    result = advisor_rules.evaluate(
        _input(4_000_000, [4_400_000, 4_600_000, 4_500_000], transactions=transactions)
    )
    assert result.verdict == "adjust_budget"
    assert result.evidence.irregular_total == 100_000
    assert result.evidence.irregular_share_pct == 20.0
    assert result.evidence.irregular_transaction.note == "Thuốc"


def test_several_irregular_transactions_add_up_to_one_off():
    # 2 khoản bất thường 200.000 + 150.000 = 70% phần vượt 500.000 (mỗi khoản < 60%).
    transactions = [
        _tx(200_000, "Sửa xe", "irregular"),
        _tx(150_000, "Khám bệnh", "irregular"),
        *_split(4_150_000, 150_000),
    ]
    result = advisor_rules.evaluate(
        _input(4_000_000, [4_400_000, 4_600_000, 4_500_000], transactions=transactions)
    )
    assert result.verdict == "one_off"
    assert result.evidence.rule == "one_off_irregular"
    assert result.evidence.one_off_transaction.note == "Sửa xe"


def test_all_over_but_unstable_is_adjust_behavior():
    result = advisor_rules.evaluate(_input(4_000_000, [4_100_000, 6_000_000, 4_500_000]))
    assert result.verdict == "adjust_behavior"
    assert result.evidence.rule == "unstable_overspend"
    assert result.evidence.all_over_planned is True
    assert result.evidence.cv_pct > 15


def test_cv_exactly_at_threshold_is_stable():
    # 2 tháng: mean 1.000.000, population std 150.000 → CV = 15% đúng ngưỡng (<=).
    values = [850_000, 1_150_000]
    assert advisor_rules.cv_squared(values) == Fraction(9, 400)
    th = Thresholds.from_settings(
        advisor_rules.DEFAULT_SETTINGS.model_copy(update={"min_history_months": 2})
    )
    result = advisor_rules.evaluate(
        _input(800_000, values, transactions=_split(1_150_000, 50_000)), th
    )
    assert result.verdict == "adjust_budget"
    assert result.evidence.cv_pct == 15.0
    assert result.evidence.proposed_planned_amount == 1_000_000
    # Cao hơn ngưỡng một chút → không còn ổn định.
    unstable = advisor_rules.evaluate(
        _input(800_000, [849_999, 1_150_000], transactions=_split(1_150_000, 50_000)), th
    )
    assert unstable.verdict == "adjust_behavior"


def test_proposed_amount_rounds_half_up_to_step():
    result = advisor_rules.evaluate(
        _input(
            4_000_000, [4_400_000, 4_450_000, 4_460_000], transactions=_split(4_460_000, 150_000)
        )
    )
    assert result.verdict == "adjust_budget"
    assert result.evidence.history_median == 4_450_000
    assert result.evidence.proposed_planned_amount == 4_500_000


def test_thresholds_from_settings():
    settings = AdvisorSettings(
        one_off_share_threshold=0.5,
        stable_cv_threshold=0.05,
        min_history_months=2,
        budget_rounding_step=50_000,
    )
    th = Thresholds.from_settings(settings)
    assert (th.one_off_share, th.stable_cv) == (Fraction(1, 2), Fraction(1, 20))
    result = advisor_rules.evaluate(_input(4_000_000, [4_400_000, 4_420_000]), th)
    assert result.verdict == "adjust_budget"
    assert result.evidence.proposed_planned_amount == 4_400_000
    assert result.evidence.history_months == 2
    assert result.evidence.one_off_share_threshold_pct == 50.0


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([3], Fraction(3)),
        ([1, 3], Fraction(2)),
        ([5, 1, 3], Fraction(3)),
        ([4, 1, 3, 2], Fraction(5, 2)),
    ],
)
def test_median(values, expected):
    assert advisor_rules.median(values) == expected


def test_cv_squared_edge_cases():
    assert advisor_rules.cv_squared([]) is None
    assert advisor_rules.cv_squared([0, 0, 0]) is None
    assert advisor_rules.cv_squared([5, 5, 5]) == 0


def test_default_settings_match_docs():
    assert advisor_rules.DEFAULT_SETTINGS.model_dump() == {
        "one_off_share_threshold": 0.6,
        "stable_cv_threshold": 0.15,
        "min_history_months": 3,
        "budget_rounding_step": 100_000,
    }


# ---------- văn bản (advice_narrative) ----------

CASES = {
    "adjust_budget": _input(4_000_000, [4_400_000, 4_600_000, 4_500_000]),
    "one_off": _input(
        2_000_000,
        [8_000_000],
        transactions=[_tx(6_500_000, "Laptop", "irregular", 12), *_split(1_500_000, 500_000)],
        label="Mua sắm",
    ),
    "adjust_behavior": _input(
        1_000_000,
        [800_000, 1_600_000, 1_400_000],
        transactions=_split(1_400_000, 200_000),
        label="Giải trí",
    ),
    "insufficient": _input(4_000_000, [0, 4_400_000, 4_300_000], empty_months=1),
    "on_track": _input(1_000_000, [700_000], label="Đi lại"),
    "comfort": _input(4_000_000, [4_400_000, 4_600_000, 4_300_000], comfort_high=4_500_000),
}


@pytest.mark.parametrize("name", list(CASES))
def test_template_always_passes_validation(name):
    result = advisor_rules.evaluate(CASES[name])
    narrative = advice_narrative.template_explanation(result.verdict, result.evidence)
    assert narrative.generated_by == "template"
    assert advice_narrative.validate_explanation(narrative, result.verdict, result.evidence) == []
    assert narrative.observation.startswith(result.evidence.allocation_label)


def test_template_texts_by_verdict():
    budget = advisor_rules.evaluate(CASES["adjust_budget"])
    text = advice_narrative.join_text(
        advice_narrative.template_explanation(budget.verdict, budget.evidence)
    )
    assert "4.400.000 ₫ / 4.600.000 ₫ / 4.500.000 ₫" in text
    assert "Nếu bạn xác nhận, app sẽ đặt ngân sách Ăn uống tháng sau thành 4.500.000 ₫" in text

    one_off = advisor_rules.evaluate(CASES["one_off"])
    text = advice_narrative.join_text(
        advice_narrative.template_explanation(one_off.verdict, one_off.evidence)
    )
    assert "“Laptop” 6.500.000 ₫" in text and "khoản một lần" in text
    assert "vượt 6.000.000 ₫ so với kế hoạch 2.000.000 ₫" in text

    comfort = advisor_rules.evaluate(CASES["comfort"])
    obs = advice_narrative.template_explanation(comfort.verdict, comfort.evidence).observation
    assert "vẫn trong vùng an toàn tới 4.500.000 ₫" in obs


def _out(**kwargs) -> BudgetAdviceExplanation:
    base = {
        "observation": "Ăn uống tháng 10/2026: thực chi 4.500.000 ₫, vượt 500.000 ₫.",
        "explanation": "3 tháng gần nhất đều vượt kế hoạch: 4.400.000 ₫ / 4.600.000 ₫ / "
        "4.500.000 ₫.",
        "action": "Nếu bạn xác nhận, app sẽ đặt ngân sách tháng sau thành 4.500.000 ₫.",
        "tone": "neutral",
    }
    return BudgetAdviceExplanation(**{**base, **kwargs})


def test_validate_accepts_good_ai_output():
    r = advisor_rules.evaluate(CASES["adjust_budget"])
    assert advice_narrative.validate_explanation(_out(), r.verdict, r.evidence) == []


def test_validate_rejects_invented_numbers_and_judgement():
    r = advisor_rules.evaluate(CASES["adjust_budget"])
    problems = advice_narrative.validate_explanation(
        _out(explanation="Bạn tiêu quá nhiều, lãng phí 1.200.000 ₫ mỗi tháng."),
        r.verdict,
        r.evidence,
    )
    assert any("1.200.000" in p for p in problems)
    assert any("bạn tiêu quá nhiều" in p for p in problems)
    assert any("lãng phí" in p for p in problems)


def test_validate_requires_proposed_amount_and_conditional_action():
    r = advisor_rules.evaluate(CASES["adjust_budget"])
    problems = advice_narrative.validate_explanation(
        _out(
            explanation="3 tháng gần nhất đều vượt kế hoạch.",
            action="Tôi đã điều chỉnh ngân sách tháng sau.",
        ),
        r.verdict,
        r.evidence,
    )
    assert any("planned đề xuất" in p for p in problems)
    assert any("có điều kiện" in p for p in problems)
    assert any("tôi đã điều chỉnh" in p for p in problems)


def test_validate_one_off_must_name_transaction_and_not_raise_budget():
    r = advisor_rules.evaluate(CASES["one_off"])
    out = _out(
        observation="Mua sắm tháng 10/2026: thực chi 8.000.000 ₫, vượt 6.000.000 ₫.",
        explanation="Chi mua sắm cao hơn kế hoạch.",
        action="Nếu bạn muốn, bạn có thể tăng ngân sách lên cho tháng sau.",
    )
    problems = advice_narrative.validate_explanation(out, r.verdict, r.evidence)
    assert any("giao dịch ngoại lệ" in p and "6.500.000" in p for p in problems)
    assert any("tăng ngân sách lên" in p for p in problems)


def test_validate_on_track_allows_missing_action():
    r = advisor_rules.evaluate(CASES["on_track"])
    out = _out(
        observation="Đi lại tháng 10/2026: thực chi 700.000 ₫ / kế hoạch 1.000.000 ₫.",
        explanation="Đang trong kế hoạch.",
        action=None,
    )
    assert advice_narrative.validate_explanation(out, r.verdict, r.evidence) == []


def test_allowed_numbers_exclude_ids():
    r = advisor_rules.evaluate(CASES["one_off"])
    payload = advice_narrative.evidence_payload(r.evidence)
    assert "transaction_id" not in str(payload)
    allowed = advice_narrative.allowed_numbers(r.evidence)
    assert {6_500_000, 6_000_000, 2_000_000, 8_000_000, 60, 15, 3, 2026, 10} <= allowed


def test_validate_rejects_technical_field_names():
    r = advisor_rules.evaluate(CASES["adjust_budget"])
    problems = advice_narrative.validate_explanation(
        _out(explanation="Hệ số biến thiên (cv_pct) là 1,8% nên verdict là adjust_budget."),
        r.verdict,
        r.evidence,
    )
    assert any("adjust_budget, cv_pct" in p for p in problems)
