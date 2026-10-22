"""Golden test diễn giải What-if (Phase 17) — OpenAI thật.

    pytest -m ai -s tests/ai_golden/test_simulator_narrative.py

Ngưỡng (phase-17 § 6, test case 8):
- Kịch bản giảm Ăn uống 20% (Laptop còn 22.000.000, để dành 4.400.000 → 4.700.000): narrative do
  AI viết (không rơi về bản mẫu), có "300.000" và "9 ngày", không "bạn phải", qua `validate`.
- Kịch bản thêm khoản định kỳ 199.000 (tiết kiệm giảm): AI viết, qua `validate`, nêu 199.000.
- Coach: "Nếu giảm ăn ngoài 20% thì sao?" → gọi `simulate`, có link /simulator, qua guard.
"""

import sys
import uuid
from datetime import date

import pytest

from app.agents import coach_graph
from app.ai import openai_client, simulator_writer
from app.schemas.goal import GoalContributionCreate, GoalCreate
from app.schemas.simulator import AddRecurringExpenseParam, ReduceCategoryParam
from app.schemas.transaction import TransactionCreate
from app.services import category_service, goal_service, simulator_narrative, transaction_service
from app.services.simulator_service import (
    BaselineSnapshot,
    CategoryInfo,
    ExpenseRow,
    GoalState,
    simulate,
)

pytestmark = [
    pytest.mark.ai,
    pytest.mark.skipif(not openai_client.is_configured(), reason="Cần OPENAI_API_KEY"),
]

FOOD = uuid.uuid4()
HOUSING = uuid.uuid4()
ENTERTAINMENT = uuid.uuid4()
START = date(2026, 10, 7)


def _report(text: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="backslashreplace").decode(encoding))


def _snapshot() -> BaselineSnapshot:
    return BaselineSnapshot(
        start_date=START,
        baseline_from=date(2026, 7, 1),
        baseline_to=date(2026, 9, 30),
        months=3,
        include_irregular=False,
        income=25_000_000,
        rows=(
            ExpenseRow(HOUSING, "Nhà ở", "essential", 19_100_000),
            ExpenseRow(FOOD, "Ăn uống", "essential", 1_500_000),
        ),
        goals=(GoalState(uuid.uuid4(), "Laptop", 1, 22_000_000, date(2027, 3, 31)),),
        categories={
            FOOD: CategoryInfo("Ăn uống", "expense", "essential"),
            HOUSING: CategoryInfo("Nhà ở", "expense", "essential"),
            ENTERTAINMENT: CategoryInfo("Giải trí", "expense", "non_essential"),
        },
    )


def _text(narrative) -> str:
    return " ".join([narrative.observation, narrative.explanation, narrative.action or ""])


def test_reduce_eating_out_narrative():
    result = simulate(
        _snapshot(), [ReduceCategoryParam(type="reduce_category", category_id=FOOD, percent=20)]
    )
    narrative, source, model = simulator_writer.write_narrative(result)
    _report(f"\n[{source} · {model}]\n{narrative.model_dump_json(indent=1)}")
    assert source == "ai"
    text = _text(narrative)
    assert "300.000" in text
    assert "9 ngày" in text
    assert "bạn phải" not in text.lower()
    assert simulator_narrative.validate(narrative, result) == []


def test_add_subscription_narrative():
    result = simulate(
        _snapshot(),
        [
            AddRecurringExpenseParam(
                type="add_recurring_expense",
                name="Netflix",
                amount=199_000,
                category_id=ENTERTAINMENT,
            )
        ],
    )
    narrative, source, _ = simulator_writer.write_narrative(result)
    _report(f"\n[{source}]\n{narrative.model_dump_json(indent=1)}")
    assert source == "ai"
    assert "199.000" in _text(narrative)
    assert simulator_narrative.validate(narrative, result) == []


def _seed(db) -> None:
    def tx(slug: str, amount: int, day: date) -> None:
        category = category_service.get_category_by_slug(db, slug)
        transaction_service.create_transaction(
            db,
            TransactionCreate(
                direction=category.kind, amount=amount, occurred_on=day, category_id=category.id
            ),
        )

    for month in (7, 8, 9):
        tx("salary", 25_000_000, date(2026, month, 1))
        tx("housing", 19_100_000, date(2026, month, 2))
        tx("food", 1_500_000, date(2026, month, 10))
    laptop = goal_service.create_goal(
        db, GoalCreate(name="Laptop", target_amount=30_000_000, deadline=date(2027, 3, 31)), START
    )
    goal_service.add_contribution(db, laptop.id, GoalContributionCreate(amount=8_000_000), START)


def test_coach_what_if(db):
    _seed(db)
    answer = coach_graph.run_coach(db, "Nếu tao giảm ăn ngoài 20% thì sao?", today=START)
    tools = [(t.name, t.args) for t in answer.tool_trace]
    _report(f"\nguard={answer.metadata.guard_status} tools={tools}\n{answer.content}")
    assert "simulate" in {t.name for t in answer.tool_trace}
    assert answer.metadata.guard_status in ("passed", "rewritten")
    assert "/simulator" in answer.content
    assert "300.000" in answer.content
