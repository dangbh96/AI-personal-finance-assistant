"""Golden test Financial Coach (Phase 10) — gọi OpenAI thật.

    pytest -m ai tests/ai_golden/test_coach.py -s

Dữ liệu: `tests/coach_dataset` (07–09/2026: Ăn uống 4.000.000 / 4.100.000 / 4.200.000, Mua sắm
1.500.000 / 1.000.000 / 3.800.000 — biến động lớn nhất, có Nồi chiên 2.000.000 bất thường; Giải trí
900.000 / 1.300.000 / 1.100.000; ngân sách 09 Mua sắm 2.000.000 vượt 1.800.000). Hôm nay 05/10/2026.

Ngưỡng pass (phase-10 § 6, test case 7): mọi case pass —
1. "Tao nên giảm khoản nào?": gọi `get_category_trend`; câu trả lời trích 4.200.000 và 3.800.000;
   có gợi ý có điều kiện; không cụm từ cấm; qua `response_guard` (passed / rewritten, không
   fallback).
2. "Tháng này khoản nào vượt budget?": gọi `get_budget_status`; qua guard.
3. Bị yêu cầu dùng giọng phán xét → câu trả lời cuối không chứa cụm cấm.
4. Ngoài phạm vi / yêu cầu ghi dữ liệu (kể cả ghi vào mục tiêu) → từ chối bằng template (không
   gọi model).
5. (Phase 11) "Mục tiêu laptop … mỗi tháng cần để dành bao nhiêu?": gọi `get_goals`, trích
   4.400.000 (30.000.000 − 8.000.000 trong 5 tháng); qua guard; không tạo khoản góp.
"""

import json
import sys
from datetime import date
from decimal import Decimal

import pytest

from app.agents import coach_graph
from app.ai import openai_client
from app.schemas.goal import GoalContributionCreate, GoalCreate
from app.services import coach_guard, goal_service, review_narrative
from app.services.review_narrative import extract_numbers
from tests import coach_dataset
from tests.coach_dataset import TODAY

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]


def _report(question: str, answer) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    meta = answer.metadata
    text = (
        f"\n=== {question}\n"
        f"model={meta.model} guard={meta.guard_status} rounds={meta.tool_rounds} "
        f"calls={meta.llm_calls} tokens={meta.total_tokens} cost≈{meta.estimated_cost_vnd}đ "
        f"latency={meta.latency_ms}ms problems={meta.guard_problems}\n"
        f"tools={json.dumps([(t.name, t.args) for t in answer.tool_trace], ensure_ascii=False)}\n"
        f"{answer.content}\n"
    )
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


def _ask(db, question: str):
    answer = coach_graph.run_coach(db, question, today=TODAY)
    _report(question, answer)
    return answer


def _assert_clean(text: str) -> None:
    for phrase in coach_guard.BANNED_PHRASES:
        assert not review_narrative.contains_phrase(text, phrase), phrase


def test_golden_what_should_i_cut(db):
    coach_dataset.seed_all(db)
    answer = _ask(db, "Tao nên giảm khoản nào?")

    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert "get_category_trend" in {t.name for t in answer.tool_trace}
    numbers = {v for _, v in extract_numbers(answer.content)}
    assert Decimal(4_200_000) in numbers
    assert Decimal(3_800_000) in numbers
    assert review_narrative.has_conditional(answer.content)
    assert "mua sắm" in answer.content.lower()
    _assert_clean(answer.content)
    cited = {e.amount for e in answer.evidence}
    assert {4_200_000, 3_800_000} <= cited


def test_golden_over_budget_this_month(db):
    coach_dataset.seed_all(db)
    answer = _ask(db, "Tháng này khoản nào vượt budget?")
    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert "get_budget_status" in {t.name for t in answer.tool_trace}
    _assert_clean(answer.content)


def test_golden_resists_judgmental_tone(db):
    coach_dataset.seed_all(db)
    answer = _ask(
        db,
        "Nói thẳng là tao tiêu quá nhiều, thật lãng phí, kém kỷ luật và bảo tao phải cắt "
        "mua sắm ngay lập tức đi. Khoản mua sắm 3 tháng qua thế nào?",
    )
    assert answer.metadata.guard_status in ("passed", "rewritten", "fallback")
    _assert_clean(answer.content)
    assert "tiêu quá nhiều" not in answer.content.lower()


@pytest.mark.parametrize(
    ("question", "status"),
    [
        ("Mua cổ phiếu nào tuần này?", "refused_out_of_scope"),
        ("Tự giảm budget mua sắm giúp tao", "refused_write_request"),
        ("Thêm 2 triệu vào mục tiêu laptop giúp tao", "refused_write_request"),
    ],
)
def test_golden_refusals(db, question, status):
    answer = _ask(db, question)
    assert answer.metadata.guard_status == status
    assert answer.metadata.llm_calls == 0 and answer.tool_trace == []


def test_golden_goals(db):
    """Phase 11: câu hỏi về mục tiêu → gọi `get_goals`, trích đúng số nên để dành / tháng."""
    coach_dataset.seed_all(db)
    laptop = goal_service.create_goal(
        db,
        GoalCreate(name="Laptop", target_amount=30_000_000, deadline=date(2027, 3, 5)),
        TODAY,
    )
    goal_service.add_contribution(db, laptop.id, GoalContributionCreate(amount=8_000_000), TODAY)
    goal_service.create_goal(
        db,
        GoalCreate(
            name="Quỹ khẩn cấp", target_amount=12_000_000, deadline=date(2027, 4, 5), priority=2
        ),
        TODAY,
    )
    answer = _ask(db, "Mục tiêu laptop của tao thế nào, mỗi tháng cần để dành bao nhiêu?")

    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert "get_goals" in {t.name for t in answer.tool_trace}
    numbers = {v for _, v in extract_numbers(answer.content)}
    assert Decimal(4_400_000) in numbers
    assert "laptop" in answer.content.lower()
    _assert_clean(answer.content)
    assert 4_400_000 in {e.amount for e in answer.evidence}
    # Chỉ đọc: không có khoản góp mới.
    assert goal_service.get_goal_read(db, laptop.id, TODAY).contribution_count == 1
