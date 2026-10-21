"""Metrics, highlights và kiểm tra narrative của review — hàm thuần, không cần DB / OpenAI."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.errors import DomainError
from app.schemas.review import ReviewMetrics, ReviewNarrativeOutput
from app.services import review_metrics, review_narrative
from app.services.review_metrics import change_pct, period_range, time_bucket
from tests.review_dataset import (
    DINNERS,
    WEEK_1,
    WEEK_1_ITEMS,
    WEEK_2,
    WEEK_2_ITEMS,
    Item,
    to_rows,
)

TODAY = date(2026, 10, 20)


def _metrics(items_2=WEEK_2_ITEMS, items_1=WEEK_1_ITEMS, today=TODAY) -> ReviewMetrics:
    current, previous = to_rows(items_2), to_rows(items_1)
    period = review_metrics.compute_period_metrics("week", WEEK_2, current, previous, today)
    highlights = review_metrics.detect_highlights(period, current)
    return ReviewMetrics(**period.model_dump(), highlights=highlights)


def _narrative(**overrides) -> ReviewNarrativeOutput:
    data = {
        "observation": "Tuần này bạn chi 2.242.000 ₫, cao hơn tuần trước 18% (1.900.000 ₫).",
        "explanation": "Phần lớn mức tăng đến từ Ăn uống: 1.180.000 ₫, tăng 18%.",
        "notice": ["4 lần ăn tối, tổng 620.000 ₫."],
        "action": "Nếu bạn muốn, bạn có thể cân nhắc đặt giới hạn cho các bữa tối bên ngoài.",
        "reflection_question": "Có khoản nào trong tuần này bạn thấy không đáng tiền không?",
        "tone": "neutral",
    }
    return ReviewNarrativeOutput(**{**data, **overrides})


# ---------- kỳ & % thay đổi ----------


def test_period_range_week_and_month():
    week = period_range("week", WEEK_2)
    assert (week.start, week.end) == (WEEK_2, date(2026, 10, 18))
    assert (week.previous_start, week.previous_end) == (WEEK_1, date(2026, 10, 11))
    month = period_range("month", date(2026, 3, 1))
    assert (month.previous_start, month.previous_end) == (date(2026, 2, 1), date(2026, 2, 28))
    assert month.end == date(2026, 3, 31)


@pytest.mark.parametrize(
    ("period", "start", "code"),
    [
        ("week", date(2026, 10, 13), "week_start_not_monday"),
        ("month", date(2026, 10, 2), "month_not_first_day"),
        ("year", date(2026, 1, 1), "invalid_review_period"),
    ],
)
def test_period_range_rejects_invalid_start(period, start, code):
    with pytest.raises(DomainError) as exc:
        period_range(period, start)
    assert exc.value.code == code


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [
        (2_242_000, 1_900_000, 18),
        (1_180_000, 1_000_000, 18),
        (1_005, 1_000, 1),  # 0,5 → làm tròn half-up
        (995, 1_000, -1),  # -0,5 → -1 (ra xa 0)
        (850_000, 1_000_000, -15),
        (500, 0, None),
        (0, 0, None),
    ],
)
def test_change_pct(current, previous, expected):
    assert change_pct(current, previous) == expected


# ---------- metrics tuần (test case 1, 4) ----------


def test_week_totals_and_change():
    m = _metrics()
    assert (m.income, m.expense, m.net) == (0, 2_242_000, -2_242_000)
    assert (m.previous_income, m.previous_expense) == (0, 1_900_000)
    assert m.expense_change == 342_000
    assert m.expense_change_pct == 18
    assert m.expense_count == len(WEEK_2_ITEMS)
    assert (m.period_start, m.period_end) == (WEEK_2, date(2026, 10, 18))


def test_week_breakdown_by_spending_type():
    m = _metrics()
    assert m.by_spending_type.model_dump() == {
        "essential": 1_420_000,
        "non_essential": 672_000,
        "irregular": 150_000,
    }
    assert m.previous_by_spending_type.model_dump() == {
        "essential": 1_550_000,
        "non_essential": 350_000,
        "irregular": 0,
    }


def test_by_category_sorted_and_includes_previous_only_categories():
    m = _metrics()
    assert [c.slug for c in m.by_category] == [
        "food",
        "utilities",
        "transport",
        "health",
        "entertainment",
        "shopping",
    ]
    shopping = m.by_category[-1]
    assert (shopping.amount, shopping.previous_amount, shopping.change) == (0, 150_000, -150_000)
    assert shopping.change_pct == -100
    health = next(c for c in m.by_category if c.slug == "health")
    assert health.change_pct is None


def test_partial_week_progress():
    m = _metrics(today=date(2026, 10, 14))
    assert (m.days_elapsed, m.days_in_period, m.complete) == (3, 7, False)
    assert m.as_of == date(2026, 10, 14)
    done = _metrics(today=date(2026, 10, 18))
    assert (done.days_elapsed, done.complete, done.as_of) == (7, True, date(2026, 10, 18))


# ---------- highlights (test case 2, 3) ----------


def test_highlight_top_increase_is_food_plus_18_percent():
    h = _metrics().highlights
    assert h.top_increase is not None
    assert (h.top_increase.slug, h.top_increase.change_pct) == ("food", 18)
    assert h.top_increase.change == 180_000
    assert h.top_decrease is not None and h.top_decrease.slug == "shopping"
    assert [c.slug for c in h.top_categories] == ["food", "utilities", "transport"]


def test_repeated_cluster_four_dinners():
    h = _metrics().highlights
    assert len(h.repeated_clusters) == 1  # "Cơm trưa" chỉ 2 lần → dưới ngưỡng 3
    cluster = h.repeated_clusters[0]
    assert cluster.label == "Ăn uống buổi tối"
    assert cluster.time_bucket == "evening"
    assert (cluster.count, cluster.total) == (4, 620_000)
    assert cluster.category_slug == "food"
    assert len(cluster.transaction_ids) == 4


def test_keyword_cluster_and_ordering():
    coffee = tuple(
        Item(date(2026, 10, 12 + d), "food", 40_000, "Cà phê", "non_essential") for d in range(3)
    )
    grab = tuple(
        Item(date(2026, 10, 12 + d), "transport", 300_000, "Grab đi làm") for d in range(3)
    )
    clusters = review_metrics.repeated_clusters(to_rows(DINNERS + coffee + grab))
    assert [(c.label, c.count, c.total, c.time_bucket) for c in clusters] == [
        ("Grab đi làm", 3, 900_000, None),
        ("Ăn uống buổi tối", 4, 620_000, "evening"),
        ("Cà phê", 3, 120_000, None),
    ]


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("Ăn tối lẩu", "evening"),
        ("an toi voi ban", "evening"),
        ("Trà sữa đêm khuya", "evening"),
        ("Cơm trưa", "noon"),
        ("Bánh mì sáng", "morning"),
        ("Tôi mua sách", None),
        ("Đi sang nhà bạn", None),
        (None, None),
    ],
)
def test_time_bucket(note, expected):
    assert time_bucket(note) == expected


def test_top_transactions_largest_first():
    h = _metrics().highlights
    assert [(t.note, t.amount) for t in h.top_transactions] == [
        ("Tiền internet + điện", 500_000),
        ("Đổ xăng", 360_000),  # bằng tiền → giao dịch mới hơn trước
        ("Đi siêu thị", 360_000),
    ]


def test_empty_weeks():
    m = _metrics(items_2=(), items_1=())
    assert (m.expense, m.expense_change, m.expense_change_pct) == (0, 0, None)
    assert m.by_category == []
    assert m.highlights.top_increase is None
    assert m.highlights.repeated_clusters == []


# ---------- số liệu trong narrative ----------


def test_extract_numbers_vietnamese_formats():
    text = "Chi 1.180.000 ₫, tăng 18%, 0,5 triệu, 620k, 12/10/2026, 2.5tr, 4 lần, v2"
    assert [v for _, v in review_narrative.extract_numbers(text)] == [
        Decimal(1_180_000),
        Decimal(18),
        Decimal(500_000),
        Decimal(620_000),
        Decimal(12),
        Decimal(10),
        Decimal(2026),
        Decimal(2_500_000),
        Decimal(4),
    ]


def test_allowed_numbers_cover_metrics_dates_and_counts():
    allowed = review_narrative.allowed_numbers(_metrics())
    for value in (2_242_000, 1_900_000, 18, 342_000, 620_000, 4, 1_180_000, 12, 10, 2026, 0):
        assert Decimal(value) in allowed
    assert Decimal(999_000) not in allowed


def test_valid_narrative_passes():
    assert review_narrative.validate_narrative(_narrative(), _metrics()) == []


def test_narrative_with_invented_number_fails():
    problems = review_narrative.validate_narrative(
        _narrative(notice=["Bạn đã chi 999.000 ₫ cho cà phê."]), _metrics()
    )
    assert problems == ["notice[0] có số “999.000” không có trong metrics"]


def test_narrative_with_rounded_amount_fails():
    problems = review_narrative.validate_narrative(
        _narrative(observation="Tuần này bạn chi khoảng 2,24 triệu."), _metrics()
    )
    assert any("2,24 triệu" in p for p in problems)


@pytest.mark.parametrize(
    "text",
    [
        "Bạn tiêu quá nhiều cho ăn uống.",
        "Đây là khoản lãng phí.",
        "Bạn phải cắt giảm ăn tối.",
        "BẠN NÊN NGAY LẬP TỨC dừng lại.",
        "Thật phung phí.",
        "ban tieu qua nhieu",
    ],
)
def test_banned_phrases_fail(text):
    problems = review_narrative.validate_narrative(_narrative(explanation=text), _metrics())
    assert any("cụm từ phán xét" in p for p in problems)


def test_action_required_and_must_be_conditional():
    missing = review_narrative.validate_narrative(_narrative(action=None), _metrics())
    assert any("thiếu action" in p for p in missing)
    command = review_narrative.validate_narrative(
        _narrative(action="Hãy giảm ăn tối ngoài hàng."), _metrics()
    )
    assert any("có điều kiện" in p for p in command)
    income_word = review_narrative.validate_narrative(
        _narrative(action="Giảm chi để tăng thu nhập."), _metrics()
    )
    assert any("có điều kiện" in p for p in income_word)
    assert (
        review_narrative.validate_narrative(
            _narrative(action="Bạn có thể thử nấu ăn tối ở nhà."), _metrics()
        )
        == []
    )


def test_empty_week_allows_missing_action():
    empty = _metrics(items_2=(), items_1=())
    narrative = _narrative(
        observation="Tuần này chưa có giao dịch nào.",
        explanation="Chưa có dữ liệu.",
        notice=["Chưa có khoản chi nào."],
        action=None,
    )
    assert review_narrative.validate_narrative(narrative, empty) == []


# ---------- bản dự phòng ----------


@pytest.mark.parametrize(
    "metrics_args",
    [
        {},
        {"items_2": (), "items_1": ()},
        {"items_1": ()},
        {"today": date(2026, 10, 14)},
        {"items_2": WEEK_1_ITEMS[:2], "items_1": WEEK_2_ITEMS},
    ],
)
def test_fallback_narrative_always_passes_validation(metrics_args):
    metrics = _metrics(**metrics_args)
    narrative = review_narrative.fallback_narrative(metrics, "AI_NOT_CONFIGURED")
    assert narrative.fallback_used is True
    assert narrative.fallback_reason == "AI_NOT_CONFIGURED"
    assert review_narrative.validate_narrative(narrative, metrics) == []


def test_fallback_narrative_content():
    narrative = review_narrative.fallback_narrative(_metrics(), "validation_failed")
    assert narrative.observation.startswith("Tuần 12/10–18/10/2026 bạn chi 2.242.000 ₫")
    assert "cao hơn tuần trước 18%" in narrative.observation
    assert "Ăn uống" in narrative.explanation and "180.000 ₫" in narrative.explanation
    assert narrative.notice[0] == "4 khoản “Ăn uống buổi tối”, tổng 620.000 ₫."
    assert narrative.action is not None and narrative.action.startswith("Nếu bạn muốn")
