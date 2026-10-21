"""API Goals + Pay Yourself First (phase-11 § 6 test case 1–8) — DB test thật, không AI."""

from datetime import date

import pytest

from app.agents.tools import finance_tools
from app.agents.tools.registry import CoachToolContext
from app.ai import openai_client
from app.models import GoalContribution
from app.schemas.budget import BudgetCreate
from app.services import budget_service, coach_evidence, goal_service

TODAY = date(2026, 10, 22)
Q = f"?today={TODAY.isoformat()}"
DEADLINE_5_MONTHS = "2027-03-22"


@pytest.fixture
def salary_id(categories) -> str:
    return categories["salary"]["id"]


def _goal(client, name="Laptop", target=30_000_000, deadline=DEADLINE_5_MONTHS, priority=1):
    resp = client.post(
        f"/api/v1/goals{Q}",
        json={"name": name, "target_amount": target, "deadline": deadline, "priority": priority},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _contribute(client, goal_id: str, amount: int, day: str = "2026-10-01"):
    resp = client.post(
        f"/api/v1/goals/{goal_id}/contributions{Q}",
        json={"amount": amount, "contributed_on": day},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _tx(client, category_id: str, amount: int, direction="income", day="2026-10-22"):
    resp = client.post(
        "/api/v1/transactions",
        json={
            "direction": direction,
            "amount": amount,
            "occurred_on": day,
            "category_id": category_id,
            "note": "Lương" if direction == "income" else "Đi chợ",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _pyf_budget(db, savings_target=5_000_000, month=date(2026, 10, 1), strategy="pyf"):
    allocations = budget_service.create_pyf_budget(25_000_000, savings_target)
    return budget_service.create_budget(
        db,
        BudgetCreate(
            period_month=month,
            strategy=strategy,
            expected_income=25_000_000,
            status="active",
            allocations=allocations,
        ),
    )


def _proposal(client, income_id: str, **extra):
    return client.post(
        f"/api/v1/goals/pyf-proposal{Q}", json={"income_transaction_id": income_id, **extra}
    )


def _allocate(client, income_id: str, items: list[tuple[str, int]], budget_savings: int = 0):
    return client.post(
        f"/api/v1/goals/allocations{Q}",
        json={
            "income_transaction_id": income_id,
            "items": [{"goal_id": g, "amount": a} for g, a in items],
            "budget_savings_amount": budget_savings,
        },
    )


def _contribution_count(db) -> int:
    return db.query(GoalContribution).count()


# ---------- CRUD + toán goal ----------


def test_case_1_goal_with_contributions(client):
    goal = _goal(client)
    assert goal["current_amount"] == 0 and goal["status"] == "active"
    assert goal["suggested_monthly_saving"] == 6_000_000
    _contribute(client, goal["id"], 8_000_000)

    detail = client.get(f"/api/v1/goals/{goal['id']}{Q}").json()
    g = detail["goal"]
    assert (g["current_amount"], g["remaining_amount"], g["months_remaining"]) == (
        8_000_000,
        22_000_000,
        5,
    )
    assert g["suggested_monthly_saving"] == 4_400_000
    assert g["on_track"] is True and g["overdue"] is False and g["progress_pct"] == 26.7
    assert g["contribution_count"] == 1 and g["last_contributed_on"] == "2026-10-01"
    [c] = detail["contributions"]
    assert c["amount"] == 8_000_000 and c["income_transaction_id"] is None


def test_case_2_reaching_target_marks_achieved(client):
    goal = _goal(client, "Quỹ khẩn cấp", 10_000_000)
    _contribute(client, goal["id"], 10_000_000)
    g = client.get(f"/api/v1/goals/{goal['id']}{Q}").json()["goal"]
    assert (g["remaining_amount"], g["suggested_monthly_saving"], g["status"]) == (
        0,
        0,
        "achieved",
    )
    assert g["progress_pct"] == 100.0 and g["on_track"] is True
    # Đã đạt → không nhận thêm khoản góp.
    resp = client.post(f"/api/v1/goals/{goal['id']}/contributions{Q}", json={"amount": 1_000})
    assert resp.status_code == 422 and resp.json()["code"] == "goal_not_active"


def test_list_order_filter_and_total(client):
    laptop = _goal(client, "Laptop", priority=2)
    emergency = _goal(client, "Quỹ khẩn cấp", 12_000_000, "2027-04-30", priority=1)
    trip = _goal(client, "Du lịch", 5_000_000, "2027-06-30", priority=1)
    client.patch(f"/api/v1/goals/{trip['id']}{Q}", json={"status": "paused"})

    data = client.get(f"/api/v1/goals{Q}").json()
    assert [g["name"] for g in data["items"]] == ["Quỹ khẩn cấp", "Laptop", "Du lịch"]
    # Chỉ cộng goal active: 12.000.000 / 6 = 2.000.000; 30.000.000 / 5 = 6.000.000.
    assert data["total_suggested_monthly_saving"] == 8_000_000
    active = client.get(f"/api/v1/goals{Q}&status=active").json()["items"]
    assert {g["id"] for g in active} == {laptop["id"], emergency["id"]}
    paused = client.get(f"/api/v1/goals{Q}&status=paused").json()["items"]
    assert [g["id"] for g in paused] == [trip["id"]]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"name": "", "target_amount": 1, "deadline": DEADLINE_5_MONTHS}, "validation_error"),
        ({"name": "X", "target_amount": 0, "deadline": DEADLINE_5_MONTHS}, "validation_error"),
        ({"name": "X", "target_amount": 1.5, "deadline": DEADLINE_5_MONTHS}, "validation_error"),
        (
            {"name": "X", "target_amount": 1, "deadline": DEADLINE_5_MONTHS, "priority": 0},
            "validation_error",
        ),
        (
            {"name": "X", "target_amount": 1, "deadline": DEADLINE_5_MONTHS, "current": 5},
            "validation_error",
        ),
        ({"name": "X", "target_amount": 1, "deadline": "2026-10-21"}, "deadline_in_past"),
    ],
)
def test_create_validation(client, body, code):
    resp = client.post(f"/api/v1/goals{Q}", json=body)
    assert resp.status_code == 422 and resp.json()["code"] == code


def test_update_goal(client):
    goal = _goal(client)
    _contribute(client, goal["id"], 8_000_000)
    url = f"/api/v1/goals/{goal['id']}{Q}"

    resp = client.patch(url, json={"name": "Laptop mới", "priority": 3, "deadline": "2027-08-01"})
    assert resp.status_code == 200, resp.text
    g = resp.json()
    assert (g["name"], g["priority"], g["months_remaining"]) == ("Laptop mới", 3, 10)
    assert g["suggested_monthly_saving"] == 2_200_000

    resp = client.patch(url, json={"target_amount": 7_000_000})
    assert resp.status_code == 422 and resp.json()["code"] == "target_below_current"
    resp = client.patch(url, json={"deadline": "2026-01-01"})
    assert resp.status_code == 422 and resp.json()["code"] == "deadline_in_past"
    assert client.patch(url, json={"status": "done"}).status_code == 422
    assert client.patch(url, json={"current_amount": 1}).status_code == 422

    # Giảm target bằng số đã có → tự chuyển "đã đạt"; tăng lại → đang thực hiện.
    assert client.patch(url, json={"target_amount": 8_000_000}).json()["status"] == "achieved"
    assert client.patch(url, json={"target_amount": 9_000_000}).json()["status"] == "active"
    missing = "/api/v1/goals/00000000-0000-0000-0000-000000000000"
    resp = client.patch(missing, json={"name": "X"})
    assert resp.status_code == 404 and resp.json()["code"] == "goal_not_found"


def test_delete_goal_rules(client):
    empty = _goal(client, "Trống")
    assert client.delete(f"/api/v1/goals/{empty['id']}").status_code == 204
    assert client.get(f"/api/v1/goals/{empty['id']}").status_code == 404

    funded = _goal(client)
    _contribute(client, funded["id"], 1_000_000)
    resp = client.delete(f"/api/v1/goals/{funded['id']}")
    assert resp.status_code == 409 and resp.json()["code"] == "goal_has_contributions"
    client.patch(f"/api/v1/goals/{funded['id']}{Q}", json={"status": "paused"})
    assert client.delete(f"/api/v1/goals/{funded['id']}").status_code == 204


def test_manual_contribution_rules(client):
    goal = _goal(client, target=5_000_000)
    url = f"/api/v1/goals/{goal['id']}/contributions{Q}"
    resp = client.post(url, json={"amount": 6_000_000})
    assert resp.status_code == 422 and resp.json()["code"] == "allocation_exceeds_remaining"
    resp = client.post(url, json={"amount": 1_000, "contributed_on": "2026-10-23"})
    assert resp.status_code == 422 and resp.json()["code"] == "contribution_in_future"
    assert client.post(url, json={"amount": 0}).status_code == 422

    c = client.post(url, json={"amount": 5_000_000}).json()
    assert c["contributed_on"] == TODAY.isoformat()
    assert client.get(f"/api/v1/goals/{goal['id']}{Q}").json()["goal"]["status"] == "achieved"
    # Xoá khoản góp → thiếu tiền → quay lại "đang thực hiện".
    assert client.delete(f"/api/v1/goals/{goal['id']}/contributions/{c['id']}").status_code == 204
    g = client.get(f"/api/v1/goals/{goal['id']}{Q}").json()["goal"]
    assert (g["status"], g["current_amount"]) == ("active", 0)
    resp = client.delete(f"/api/v1/goals/{goal['id']}/contributions/{c['id']}")
    assert resp.status_code == 404 and resp.json()["code"] == "goal_contribution_not_found"

    client.patch(f"/api/v1/goals/{goal['id']}{Q}", json={"status": "paused"})
    resp = client.post(url, json={"amount": 1_000})
    assert resp.status_code == 422 and resp.json()["code"] == "goal_not_active"


# ---------- PYF ----------


def test_case_3_proposal_with_budget_savings(client, db, salary_id):
    laptop = _goal(client, "Laptop", priority=1)
    _contribute(client, laptop["id"], 8_000_000)
    emergency = _goal(client, "Quỹ khẩn cấp", 12_000_000, "2027-04-30", priority=2)
    _pyf_budget(db)
    income = _tx(client, salary_id, 25_000_000)
    before = _contribution_count(db)

    resp = _proposal(client, income["id"])
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert [(i["goal_id"], i["amount"]) for i in p["items"]] == [
        (laptop["id"], 4_400_000),
        (emergency["id"], 2_000_000),
    ]
    assert p["items"][0]["remaining_after"] == 17_600_000
    assert (p["income_amount"], p["budget_savings_target"], p["budget_savings_amount"]) == (
        25_000_000,
        5_000_000,
        5_000_000,
    )
    assert (p["goal_total"], p["allocated_total"], p["available_spending"]) == (
        6_400_000,
        11_400_000,
        13_600_000,
    )
    assert p["budget_strategy"] == "pyf" and p["budget_month"] == "2026-10-01"
    assert p["valid"] is True and p["warnings"] == []
    # Đề xuất không ghi DB.
    assert _contribution_count(db) == before


def test_case_4_income_smaller_than_needs(client, db, salary_id):
    laptop = _goal(client)
    _contribute(client, laptop["id"], 8_000_000)
    _pyf_budget(db)
    income = _tx(client, salary_id, 5_000_000)
    p = _proposal(client, income["id"]).json()
    assert [i["amount"] for i in p["items"]] == [4_400_000]
    assert (p["budget_savings_amount"], p["available_spending"]) == (600_000, 0)


def test_case_5_confirm_allocation(client, db, salary_id):
    laptop = _goal(client)
    _contribute(client, laptop["id"], 8_000_000)
    income = _tx(client, salary_id, 25_000_000)

    resp = _allocate(client, income["id"], [(laptop["id"], 4_400_000)], budget_savings=5_000_000)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    [c] = data["contributions"]
    assert (c["amount"], c["income_transaction_id"], c["contributed_on"]) == (
        4_400_000,
        income["id"],
        "2026-10-22",
    )
    assert c["income_transaction"]["amount"] == 25_000_000
    assert c["income_transaction"]["category_name"] == "Lương"
    assert (data["goal_total"], data["budget_savings_amount"], data["available_spending"]) == (
        4_400_000,
        5_000_000,
        15_600_000,
    )
    assert data["goals"][0]["current_amount"] == 12_400_000

    detail = client.get(f"/api/v1/goals/{laptop['id']}{Q}").json()
    assert detail["goal"]["current_amount"] == 12_400_000
    assert detail["contributions"][0]["income_transaction_id"] == income["id"]

    # Thu nhập đã phân bổ → không xác nhận / đề xuất lại.
    resp = _allocate(client, income["id"], [(laptop["id"], 100_000)])
    assert resp.status_code == 409 and resp.json()["code"] == "income_already_allocated"
    resp = _proposal(client, income["id"])
    assert resp.status_code == 409 and resp.json()["code"] == "income_already_allocated"


def test_case_6_invalid_income(client, categories):
    goal = _goal(client)
    expense = _tx(client, categories["food"]["id"], 100_000, direction="expense")
    resp = _allocate(client, expense["id"], [(goal["id"], 100_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "transaction_not_income"
    missing = "00000000-0000-0000-0000-000000000000"
    resp = _allocate(client, missing, [(goal["id"], 100_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "income_transaction_not_found"
    resp = _proposal(client, expense["id"])
    assert resp.status_code == 422 and resp.json()["code"] == "transaction_not_income"


def test_case_7_over_income_creates_nothing(client, db, salary_id):
    laptop = _goal(client, target=30_000_000)
    emergency = _goal(client, "Quỹ khẩn cấp", 30_000_000, priority=2)
    income = _tx(client, salary_id, 25_000_000)
    before = _contribution_count(db)
    resp = _allocate(
        client, income["id"], [(laptop["id"], 20_000_000), (emergency["id"], 6_000_000)]
    )
    assert resp.status_code == 422 and resp.json()["code"] == "allocation_exceeds_income"
    resp = _allocate(client, income["id"], [(laptop["id"], 21_000_000)], budget_savings=5_000_000)
    assert resp.status_code == 422 and resp.json()["code"] == "allocation_exceeds_income"
    assert _contribution_count(db) == before
    # Goal thứ hai vượt phần còn thiếu → cũng không ghi goal thứ nhất.
    small = _goal(client, "Nhỏ", 1_000_000, priority=3)
    resp = _allocate(client, income["id"], [(laptop["id"], 1_000_000), (small["id"], 2_000_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "allocation_exceeds_remaining"
    assert _contribution_count(db) == before


def test_invalid_allocation_items(client, salary_id):
    goal = _goal(client)
    paused = _goal(client, "Tạm dừng", priority=2)
    client.patch(f"/api/v1/goals/{paused['id']}{Q}", json={"status": "paused"})
    income = _tx(client, salary_id, 25_000_000)

    resp = _allocate(client, income["id"], [(goal["id"], 100_000), (goal["id"], 200_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "duplicate_goal"
    resp = _allocate(client, income["id"], [(paused["id"], 100_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "goal_not_active"
    resp = _allocate(client, income["id"], [("00000000-0000-0000-0000-000000000000", 1_000)])
    assert resp.status_code == 422 and resp.json()["code"] == "goal_not_found"
    resp = _allocate(client, income["id"], [(goal["id"], -1)])
    assert resp.status_code == 422 and resp.json()["code"] == "validation_error"

    # Mọi số = 0 → không tạo khoản góp, thu nhập vẫn "chưa phân bổ".
    resp = _allocate(client, income["id"], [(goal["id"], 0)], budget_savings=5_000_000)
    assert resp.status_code == 201 and resp.json()["contributions"] == []
    assert resp.json()["available_spending"] == 20_000_000
    assert _proposal(client, income["id"]).status_code == 200


def test_proposal_recalculates_edited_amounts(client, db, salary_id):
    laptop = _goal(client)
    _contribute(client, laptop["id"], 8_000_000)
    emergency = _goal(client, "Quỹ khẩn cấp", 12_000_000, "2027-04-30", priority=2)
    _pyf_budget(db)
    income = _tx(client, salary_id, 25_000_000)

    p = _proposal(client, income["id"], items=[{"goal_id": laptop["id"], "amount": 3_000_000}])
    data = p.json()
    assert [(i["amount"], i["proposed_amount"]) for i in data["items"]] == [
        (3_000_000, 4_400_000),
        (0, 2_000_000),
    ]
    assert (data["budget_savings_amount"], data["available_spending"]) == (5_000_000, 17_000_000)

    data = _proposal(
        client,
        income["id"],
        items=[
            {"goal_id": laptop["id"], "amount": 23_000_000},
            {"goal_id": emergency["id"], "amount": 2_000_000},
        ],
        budget_savings_amount=1_000_000,
    ).json()
    assert data["valid"] is False
    assert {w["code"] for w in data["warnings"]} == {
        "allocation_exceeds_remaining",
        "allocation_exceeds_income",
    }
    assert data["items"][0]["exceeds_remaining"] is True
    assert data["items"][0]["remaining_after"] == -1_000_000
    assert data["available_spending"] == -1_000_000


def test_paused_goal_not_in_proposal(client, salary_id):
    laptop = _goal(client)
    trip = _goal(client, "Du lịch", 5_000_000, priority=2)
    client.patch(f"/api/v1/goals/{laptop['id']}{Q}", json={"status": "paused"})
    income = _tx(client, salary_id, 25_000_000)
    p = _proposal(client, income["id"]).json()
    assert [i["goal_id"] for i in p["items"]] == [trip["id"]]
    # Không có ngân sách tháng → không có dòng tiết kiệm ngân sách.
    assert (p["budget_savings_target"], p["budget_savings_amount"], p["budget_id"]) == (
        None,
        0,
        None,
    )


def test_post_transaction_attaches_proposal(client, db, salary_id, categories):
    # Chưa có goal / ngân sách pyf → không đề xuất.
    plain = client.post(
        "/api/v1/transactions",
        json={
            "direction": "income",
            "amount": 25_000_000,
            "occurred_on": "2026-10-22",
            "category_id": salary_id,
        },
    ).json()
    assert plain["pyf_proposal"] is None

    # Goal nhỏ: gợi ý/tháng = 100.000 bất kể hôm nay (POST /transactions dùng ngày server).
    goal = _goal(client, "Sổ tay", 100_000, "2030-12-31")
    income = _tx(client, salary_id, 25_000_000)
    p = income["pyf_proposal"]
    assert p is not None and p["income_transaction_id"] == income["id"]
    assert [(i["goal_id"], i["amount"]) for i in p["items"]] == [(goal["id"], 100_000)]
    assert p["available_spending"] == 24_900_000
    assert _contribution_count(db) == 0

    expense = _tx(client, categories["food"]["id"], 100_000, direction="expense")
    assert expense["pyf_proposal"] is None


def test_pyf_budget_without_goals_still_proposes(client, db, salary_id):
    _pyf_budget(db, savings_target=5_000_000, month=date(2026, 9, 1))
    income = _tx(client, salary_id, 25_000_000, day="2026-09-05")
    p = income["pyf_proposal"]
    assert p is not None and p["items"] == []
    assert (p["budget_savings_amount"], p["available_spending"]) == (5_000_000, 20_000_000)


def test_unallocated_incomes(client, salary_id):
    goal = _goal(client)
    old = _tx(client, salary_id, 1_000_000, day="2026-08-31")
    september = _tx(client, salary_id, 2_000_000, day="2026-09-01")
    october = _tx(client, salary_id, 3_000_000, day="2026-10-05")
    future = _tx(client, salary_id, 4_000_000, day="2026-10-30")
    url = f"/api/v1/goals/unallocated-incomes{Q}"
    ids = [i["id"] for i in client.get(url).json()["items"]]
    assert october["id"] in ids and september["id"] in ids
    assert old["id"] not in ids and future["id"] not in ids
    assert ids.index(october["id"]) < ids.index(september["id"])

    assert _allocate(client, october["id"], [(goal["id"], 1_000_000)]).status_code == 201
    ids = [i["id"] for i in client.get(url).json()["items"]]
    assert october["id"] not in ids


def test_income_with_contributions_is_protected(client, categories, salary_id):
    goal = _goal(client)
    income = _tx(client, salary_id, 25_000_000)
    assert _allocate(client, income["id"], [(goal["id"], 4_000_000)]).status_code == 201
    url = f"/api/v1/transactions/{income['id']}"

    resp = client.patch(url, json={"amount": 3_000_000})
    assert resp.status_code == 422 and resp.json()["code"] == "amount_below_goal_contributions"
    resp = client.patch(url, json={"direction": "expense", "category_id": categories["food"]["id"]})
    assert resp.status_code == 409 and resp.json()["code"] == "income_has_goal_contributions"
    assert client.patch(url, json={"amount": 4_000_000, "note": "Lương T10"}).status_code == 200

    # Xoá thu nhập → giữ khoản góp, bỏ liên kết.
    assert client.delete(url).status_code == 204
    detail = client.get(f"/api/v1/goals/{goal['id']}{Q}").json()
    assert detail["goal"]["current_amount"] == 4_000_000
    assert detail["contributions"][0]["income_transaction_id"] is None


# ---------- Coach tool ----------


def test_case_8_get_goals_tool_without_openai(client, db, monkeypatch):
    def _no_ai(**kwargs):
        raise AssertionError("không được gọi OpenAI")

    monkeypatch.setattr(openai_client, "_chat_tools", _no_ai)
    monkeypatch.setattr(openai_client, "_chat_json", _no_ai)
    laptop = _goal(client)
    _contribute(client, laptop["id"], 8_000_000)
    _goal(client, "Quỹ khẩn cấp", 12_000_000, "2027-04-30", priority=2)
    paused = _goal(client, "Du lịch", 5_000_000, priority=3)
    client.patch(f"/api/v1/goals/{paused['id']}{Q}", json={"status": "paused"})

    ctx = CoachToolContext(db=db, today=TODAY)
    tool = next(t for t in finance_tools.default_registry().build(ctx) if t.name == "get_goals")
    ctx.recorder.begin("c1", "get_goals", {})
    raw = tool.invoke({})
    ctx.recorder.finish("c1", 3, None)
    output = ctx.recorder.ordered()[0].output
    assert output is not None and '"total_suggested_monthly_saving":6400000' in raw
    assert [g.name for g in output.active_goals] == ["Laptop", "Quỹ khẩn cấp"]
    assert [g.suggested_monthly_saving for g in output.active_goals] == [4_400_000, 2_000_000]
    assert (output.paused_count, output.achieved_count) == (1, 0)
    assert output.active_goals[0].remaining_amount == 22_000_000

    rows = coach_evidence.evidence_rows("get_goals", output)
    assert ("Laptop", "Nên để dành / tháng", 4_400_000) in {
        (r.label, r.metric, r.amount) for r in rows
    }
    assert coach_evidence.summarize_result(output) == ("2 mục tiêu đang thực hiện", 2)
    # Tool chỉ đọc.
    assert _contribution_count(db) == 1


def test_get_goals_overview_empty(db):
    out = goal_service.get_goals_overview(db, TODAY)
    assert out.active_goals == [] and out.total_suggested_monthly_saving == 0
    assert "/goals" in (out.note or "")
    assert coach_evidence.summarize_result(out) == ("Chưa có mục tiêu đang thực hiện", 0)
