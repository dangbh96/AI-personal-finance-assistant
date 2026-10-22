"""API What-if simulator (Phase 17 § 6) — DB test thật, AI giả (không cần key)."""

import json
from datetime import date

import pytest
from sqlalchemy import func, select

from app.agents.tools import finance_tools
from app.agents.tools.registry import CoachToolContext
from app.ai import openai_client
from app.models import Budget, Goal, GoalContribution, Scenario, Transaction
from app.schemas.budget import BudgetAllocationInput, BudgetCreate
from app.schemas.coach import SimulateOutput
from app.schemas.goal import GoalContributionCreate, GoalCreate
from app.schemas.transaction import TransactionCreate
from app.services import (
    budget_service,
    category_service,
    coach_evidence,
    goal_service,
    transaction_service,
)
from tests.api.test_coach import call, result

URL = "/api/v1/simulator"
TODAY = date(2026, 10, 7)
Q = {"today": TODAY.isoformat()}


def _tx(db, slug: str, amount: int, day: date, spending_type: str | None = None, note=""):
    category = category_service.get_category_by_slug(db, slug)
    transaction_service.create_transaction(
        db,
        TransactionCreate(
            direction=category.kind,
            amount=amount,
            occurred_on=day,
            category_id=category.id,
            spending_type=spending_type,
            note=note,
        ),
    )


@pytest.fixture
def seeded(db) -> dict:
    """07–09/2026 mỗi tháng: lương 25.000.000, nhà 19.100.000, ăn uống 1.500.000 → để dành
    4.400.000; tháng 8 thêm sửa xe 3.000.000 (bất thường). Laptop 30.000.000, đã góp 8.000.000."""
    for month in (7, 8, 9):
        _tx(db, "salary", 25_000_000, date(2026, month, 1))
        _tx(db, "housing", 19_100_000, date(2026, month, 2))
        _tx(db, "food", 900_000, date(2026, month, 10), note="Ăn ngoài")
        _tx(db, "food", 600_000, date(2026, month, 20), note="Nhà hàng")
    _tx(db, "transport", 3_000_000, date(2026, 8, 15), "irregular", "Sửa xe")
    laptop = goal_service.create_goal(
        db, GoalCreate(name="Laptop", target_amount=30_000_000, deadline=date(2027, 3, 31)), TODAY
    )
    goal_service.add_contribution(db, laptop.id, GoalContributionCreate(amount=8_000_000), TODAY)
    food = category_service.get_category_by_slug(db, "food")
    return {"laptop": laptop, "food": food}


def _run(client, *params, **extra):
    return client.post(f"{URL}/run", params=Q, json={"params": list(params), **extra})


def reduce_food(seeded, percent=20) -> dict:
    return {"type": "reduce_category", "category_id": str(seeded["food"].id), "percent": percent}


def _counts(db) -> tuple[int, ...]:
    return tuple(
        db.scalar(select(func.count()).select_from(m))
        for m in (Transaction, Budget, Goal, GoalContribution)
    )


def test_run_eating_out_laptop_exact_numbers(client, db, seeded):
    """Test case 1–4: ăn uống 1.500.000 giảm 20% → +300.000; Laptop 150 → 141 ngày."""
    before = _counts(db)
    resp = _run(client, reduce_food(seeded))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["baseline_from"], body["baseline_to"]) == ("2026-07-01", "2026-09-30")
    assert body["baseline_monthly_income"] == 25_000_000
    assert body["baseline_monthly_expense"] == 20_600_000  # bỏ khoản bất thường
    assert body["baseline_monthly_savings"] == 4_400_000
    assert body["delta_monthly_savings"] == 300_000
    assert body["projected_monthly_savings"] == 4_700_000
    goal = body["goal_impacts"][0]
    assert goal["name"] == "Laptop" and goal["remaining_amount"] == 22_000_000
    assert (goal["days_before"], goal["days_after"], goal["days_earlier"]) == (150, 141, 9)
    assert goal["completion_date_before"] == "2027-03-06"
    assert goal["completion_date_after"] == "2027-02-25"
    assert body["narrative"] is None
    # Chỉ mô phỏng: không ghi giao dịch / ngân sách / mục tiêu / khoản góp.
    assert _counts(db) == before


def test_run_income_and_recurring(client, db, seeded):
    """Test case 5, 6."""
    entertainment = category_service.get_category_by_slug(db, "entertainment")
    body = _run(
        client,
        {"type": "change_income", "delta_amount": 2_000_000},
        {
            "type": "add_recurring_expense",
            "name": "Netflix",
            "amount": 199_000,
            "category_id": str(entertainment.id),
        },
    ).json()
    assert [a["delta_monthly_savings"] for a in body["applied"]] == [2_000_000, -199_000]
    assert body["projected_monthly_savings"] == 4_400_000 + 2_000_000 - 199_000


def test_include_irregular_and_baseline_months(client, seeded):
    body = _run(client, reduce_food(seeded), include_irregular=True).json()
    assert body["baseline_monthly_expense"] == 21_600_000  # + 3.000.000 / 3
    one = _run(client, reduce_food(seeded), baseline_months=1).json()
    assert (one["baseline_from"], one["baseline_to"]) == ("2026-09-01", "2026-09-30")


@pytest.mark.parametrize(
    ("param", "code"),
    [
        ({"type": "reduce_category", "percent": 0}, "validation_error"),
        ({"type": "reduce_category", "percent": 150}, "validation_error"),
        ({"type": "nope"}, "validation_error"),
        ({"type": "change_income", "delta_amount": 0}, "zero_delta"),
    ],
)
def test_validation(client, seeded, param, code):
    """Test case 7: percent 0 / 150 → 422."""
    if param["type"] == "reduce_category":
        param = {**param, "category_id": str(seeded["food"].id)}
    resp = _run(client, param)
    assert resp.status_code == 422 and resp.json()["code"] == code


def test_domain_validation(client, db, seeded):
    salary = category_service.get_category_by_slug(db, "salary")
    cases = [
        ({"type": "reduce_category", "category_id": str(salary.id), "percent": 10}, None),
        (
            {
                "type": "reduce_category",
                "category_id": "00000000-0000-0000-0000-000000000000",
                "percent": 10,
            },
            "category_not_found",
        ),
        (
            {
                "type": "change_goal_deadline",
                "goal_id": "00000000-0000-0000-0000-000000000000",
                "new_deadline": "2027-05-01",
            },
            "goal_not_active",
        ),
        (
            {
                "type": "change_goal_deadline",
                "goal_id": str(seeded["laptop"].id),
                "new_deadline": "2026-10-01",
            },
            "invalid_deadline",
        ),
    ]
    for param, code in cases:
        resp = _run(client, param)
        assert resp.status_code == 422
        assert resp.json()["code"] == (code or "category_kind_mismatch")
    assert client.post(f"{URL}/run", json={"params": []}).status_code == 422
    too_many = [{"type": "change_income", "delta_amount": 1}] * 11
    assert client.post(f"{URL}/run", json={"params": too_many}).status_code == 422


def test_change_goal_deadline(client, seeded):
    body = _run(
        client,
        {
            "type": "change_goal_deadline",
            "goal_id": str(seeded["laptop"].id),
            "new_deadline": "2027-01-31",
        },
    ).json()
    goal = body["goal_impacts"][0]
    assert (goal["required_monthly_before"], goal["required_monthly_after"]) == (
        4_400_000,
        7_400_000,
    )
    assert goal["on_track_before"] is True and goal["on_track_after"] is False


def test_budget_variance_from_current_month_budget(client, db, seeded):
    budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=date(2026, 10, 1),
            strategy="fifty_thirty_twenty",
            expected_income=25_000_000,
            status="active",
            allocations=[
                BudgetAllocationInput(
                    group="essential", category_id=seeded["food"].id, planned_amount=1_400_000
                ),
                BudgetAllocationInput(
                    group="savings", jar_name="savings", planned_amount=5_000_000
                ),
            ],
        ),
    )
    body = _run(client, reduce_food(seeded)).json()
    assert body["budget_month"] == "2026-10-01"
    rows = body["budget_variance_after"]
    assert len(rows) == 1  # dòng tiết kiệm không so
    assert rows[0]["label"] == "Ăn uống"
    assert (rows[0]["variance_before"], rows[0]["variance_after"]) == (100_000, -200_000)


def test_empty_database_still_runs(client, db):
    food = category_service.get_category_by_slug(db, "food")
    body = _run(
        client, {"type": "reduce_category", "category_id": str(food.id), "percent": 10}
    ).json()
    assert body["baseline_monthly_savings"] == 0 and body["goal_impacts"] == []
    assert len(body["warnings"]) >= 3


# ---------- diễn giải ----------


def _narrative(**overrides) -> str:
    data = {
        "observation": "Giảm Ăn uống 20% giúp để dành thêm 300.000 ₫ mỗi tháng, từ 4.400.000 ₫ "
        "lên 4.700.000 ₫.",
        "explanation": "Mục tiêu Laptop đạt sau 141 ngày thay vì 150 ngày — sớm hơn 9 ngày.",
        "action": "Nếu bạn muốn, bạn có thể cân nhắc thử mức chi này trong tháng tới.",
        "caveats": ["Mô phỏng dùng mức trung bình 3 tháng, 1 tháng = 30 ngày."],
    }
    return json.dumps({**data, **overrides}, ensure_ascii=False)


def test_narrative_from_ai(client, seeded, fake_ai):
    """Test case 8 (AI giả): có 300.000 và 9 ngày, không 'bạn phải'."""
    calls, responses = fake_ai
    responses.append(_narrative())
    body = _run(client, reduce_food(seeded), with_narrative=True).json()
    assert body["narrative_source"] == "ai"
    text = json.dumps(body["narrative"], ensure_ascii=False)
    assert "300.000" in text and "9 ngày" in text and "bạn phải" not in text.lower()
    assert calls[0]["model"] == openai_client.model_fast()
    prompt = calls[0]["messages"][0]["content"]
    assert '"delta_monthly_savings": 300000' in prompt and "category_id" not in prompt


def test_narrative_invalid_twice_falls_back_to_template(client, seeded, fake_ai):
    _, responses = fake_ai
    bad = _narrative(observation="Bạn phải tiết kiệm thêm 999.999 ₫.")
    responses += [bad, bad]
    body = _run(client, reduce_food(seeded), with_narrative=True).json()
    assert body["narrative_source"] == "template" and body["narrative_model"] == "template"
    assert "999.999" not in json.dumps(body["narrative"], ensure_ascii=False)


def test_narrative_without_ai_key_uses_template(client, seeded, monkeypatch):
    monkeypatch.setattr(openai_client, "is_configured", lambda settings=None: False)
    resp = _run(client, reduce_food(seeded), with_narrative=True)
    assert resp.status_code == 200
    narrative = resp.json()["narrative"]
    assert "9 ngày" in narrative["explanation"] and resp.json()["narrative_source"] == "template"


# ---------- tool Coach `simulate` (T7) ----------


def test_coach_simulate_tool_and_evidence(db, seeded):
    ctx = CoachToolContext(db=db, today=TODAY)
    tool = finance_tools.simulate_tool(ctx)
    ctx.recorder.begin("s1", "simulate", {})
    tool.invoke({"reduce_category_slug": "food", "reduce_percent": 20})
    ctx.recorder.finish("s1", 3, None)
    output = ctx.recorder.ordered()[0].output
    assert isinstance(output, SimulateOutput)
    assert output.delta_monthly_savings == 300_000 and output.link == "/simulator"
    assert output.goals[0].days_earlier == 9 and output.changes == ["Giảm Ăn uống 20%"]
    rows = coach_evidence.evidence_rows("simulate", output)
    assert [r.amount for r in rows] == [4_400_000, 4_700_000, 300_000]
    assert coach_evidence.summarize_result(output) == ("Mô phỏng: Giảm Ăn uống 20%", 1)
    with pytest.raises(Exception, match="ít nhất một thay đổi"):
        tool.invoke({})
    with pytest.raises(Exception, match="reduce_percent"):
        tool.invoke({"reduce_category_slug": "food"})
    with pytest.raises(Exception, match="Không có danh mục"):
        tool.invoke({"reduce_category_slug": "khong_co", "reduce_percent": 10})


def test_coach_answers_what_if_with_simulate(client, db, seeded, fake_llm):
    """UI scenario 5: "Nếu giảm ăn ngoài 20% thì sao?" → Coach gọi `simulate`, link /simulator."""
    calls, responses = fake_llm
    answer = (
        "**Quan sát**\n- Đây là mô phỏng: để dành mỗi tháng từ 4.400.000 ₫ lên 4.700.000 ₫ "
        "(+300.000 ₫).\n\n**Vì sao**\nMục tiêu Laptop đạt sớm hơn 9 ngày.\n\n"
        "**Bạn có thể cân nhắc**\nNếu bạn muốn, bạn có thể thử thêm kịch bản ở "
        "[Mô phỏng](/simulator)."
    )
    responses += [
        result(
            calls=[call("simulate", {"reduce_category_slug": "food", "reduce_percent": 20}, "s1")]
        ),
        result(answer),
    ]
    session = client.post("/api/v1/coach/sessions", json={}).json()
    before = _counts(db)
    data = client.post(
        f"/api/v1/coach/sessions/{session['id']}/messages",
        json={"content": "Nếu giảm ăn ngoài 20% thì sao?", "today": TODAY.isoformat()},
    ).json()
    assert data["guard_status"] == "passed", data["assistant_message"]["metadata"]
    assert data["tool_trace"][0]["name"] == "simulate"
    assert "[Mô phỏng](/simulator)" in data["assistant_message"]["content"]
    assert {e["amount"] for e in data["evidence"]} >= {4_400_000, 4_700_000, 300_000}
    assert _counts(db) == before


# ---------- kịch bản đã lưu (T5) ----------


def test_scenarios_crud(client, db, seeded):
    resp = client.post(
        f"{URL}/scenarios",
        params=Q,
        json={"name": "Giảm ăn ngoài 20%", "params": [reduce_food(seeded)]},
    )
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["result"]["delta_monthly_savings"] == 300_000
    assert saved["params"]["params"][0]["percent"] == 20
    second = client.post(
        f"{URL}/scenarios",
        params=Q,
        json={
            "name": "Tăng thu nhập 2 triệu",
            "params": [{"type": "change_income", "delta_amount": 2_000_000}],
        },
    ).json()

    items = client.get(f"{URL}/scenarios").json()["items"]
    assert [i["name"] for i in items] == ["Tăng thu nhập 2 triệu", "Giảm ăn ngoài 20%"]
    assert db.scalar(select(func.count()).select_from(Scenario)) == 2

    assert client.delete(f"{URL}/scenarios/{second['id']}").status_code == 204
    assert [i["id"] for i in client.get(f"{URL}/scenarios").json()["items"]] == [saved["id"]]
    missing = client.delete(f"{URL}/scenarios/{second['id']}")
    assert missing.status_code == 404 and missing.json()["code"] == "scenario_not_found"
    assert client.post(f"{URL}/scenarios", json={"name": " ", "params": []}).status_code == 422
