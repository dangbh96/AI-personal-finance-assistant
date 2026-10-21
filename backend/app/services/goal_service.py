"""Goals + Pay Yourself First (Phase 11) — lõi deterministic, không gọi AI (ADR-005).

- Tiến độ goal: `current_amount` = tổng khoản góp (không lưu cột riêng), `remaining_amount`,
  `months_remaining`, `suggested_monthly_saving` (làm tròn lên bội số 100.000), `on_track`.
- `months_remaining(today, deadline)`: tính cả tháng hiện tại, không tính tháng đến hạn (tiền phải
  đủ trước tháng đến hạn); tối thiểu 1 nếu chưa quá hạn (`deadline >= today`); quá hạn → 0.
  Vd hôm nay 22/10/2026, hạn 22/03/2027 → 5 (tháng 10, 11, 12, 1, 2).
- PYF: thu nhập → trích cho goal active theo `priority` (min(gợi ý/tháng, còn thiếu, thu nhập còn
  lại)) → phần còn lại dành `savings_target` của ngân sách tháng thu nhập →
  `available_spending = income - goal_total - budget_savings_amount`.
- Đề xuất (`propose_pyf_allocation`, `proposal_for_new_income`) **không ghi DB**; chỉ
  `confirm_allocations` (user xác nhận) tạo `goal_contributions`.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import Budget, Goal, GoalContribution, Transaction
from app.repositories import budget_repository, goal_repository
from app.repositories.goal_repository import ContributionTotals
from app.schemas.coach import GetGoalsOutput, GoalToolItem
from app.schemas.goal import (
    GoalContributionCreate,
    GoalContributionRead,
    GoalCreate,
    GoalDetail,
    GoalList,
    GoalRead,
    GoalUpdate,
    IncomeBrief,
    PyfAllocationItemInput,
    PyfAllocationRequest,
    PyfAllocationResult,
    PyfProposal,
    PyfProposalItem,
    PyfProposalRequest,
    PyfWarning,
    UnallocatedIncomeList,
)
from app.services.money import add_months, format_vnd, month_range

SAVING_ROUNDING_STEP = 100_000
UNALLOCATED_LOOKBACK_MONTHS = 1
UNALLOCATED_LIMIT = 20

# ---------- toán goal (hàm thuần) ----------


def months_remaining(today: date, deadline: date) -> int:
    if deadline < today:
        return 0
    diff = (deadline.year - today.year) * 12 + deadline.month - today.month
    return max(1, diff)


def ceil_to_step(amount: int, step: int = SAVING_ROUNDING_STEP) -> int:
    """Làm tròn lên bội số `step` (amount ≥ 0)."""
    if step <= 0:
        raise ValueError("step phải > 0")
    return -(-amount // step) * step


def suggested_monthly_saving(remaining: int, months: int, step: int = SAVING_ROUNDING_STEP) -> int:
    """`ceil_to_step(remaining / months)`, không vượt `remaining`; quá hạn (months = 0) → toàn bộ
    `remaining`; đã đạt → 0. Vd 22.000.000 / 5 → 4.400.000."""
    if remaining <= 0:
        return 0
    if months <= 0:
        return remaining
    return min(remaining, -(-remaining // (months * step)) * step)


def progress_pct(current: int, target: int) -> float:
    """current / target × 100, 1 chữ số (nửa ra xa 0), tối đa 100."""
    if target <= 0:
        return 0.0
    exact = Decimal(min(current, target) * 100) / Decimal(target)
    return float(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class GoalProgress:
    current: int
    remaining: int
    progress_pct: float
    months_remaining: int
    suggested_monthly_saving: int
    on_track: bool
    overdue: bool


def compute_progress(target: int, current: int, deadline: date, today: date) -> GoalProgress:
    remaining = max(0, target - current)
    months = months_remaining(today, deadline)
    suggested = suggested_monthly_saving(remaining, months)
    overdue = remaining > 0 and deadline < today
    on_track = remaining == 0 or (not overdue and current + suggested * months >= target)
    return GoalProgress(
        current=current,
        remaining=remaining,
        progress_pct=progress_pct(current, target),
        months_remaining=months,
        suggested_monthly_saving=suggested,
        on_track=on_track,
        overdue=overdue,
    )


def plan_allocation(
    income_amount: int, needs: Sequence[tuple[int, int]], savings_target: int | None
) -> tuple[list[int], int]:
    """Chia thu nhập theo thứ tự `needs` (đã sort theo priority): mỗi goal nhận
    min(gợi ý/tháng, còn thiếu, thu nhập còn lại); phần còn lại dành tối đa `savings_target`.

    Trả `(số cho từng goal, số cho tiết kiệm ngân sách)`.
    """
    left = income_amount
    amounts = []
    for suggested, remaining in needs:
        amount = max(0, min(suggested, remaining, left))
        amounts.append(amount)
        left -= amount
    return amounts, max(0, min(savings_target or 0, left))


# ---------- đọc goal ----------


def _to_read(goal: Goal, totals: ContributionTotals, today: date) -> GoalRead:
    p = compute_progress(goal.target_amount, totals.total, goal.deadline, today)
    return GoalRead(
        id=goal.id,
        name=goal.name,
        target_amount=goal.target_amount,
        current_amount=p.current,
        remaining_amount=p.remaining,
        progress_pct=p.progress_pct,
        deadline=goal.deadline,
        months_remaining=p.months_remaining,
        suggested_monthly_saving=p.suggested_monthly_saving,
        on_track=p.on_track,
        overdue=p.overdue,
        priority=goal.priority,
        status=goal.status,  # type: ignore[arg-type]
        contribution_count=totals.count,
        last_contributed_on=totals.last_on,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def _reads(db: Session, goals: Sequence[Goal], today: date) -> list[GoalRead]:
    totals = goal_repository.contribution_totals(db, [g.id for g in goals])
    return [_to_read(g, totals.get(g.id, ContributionTotals()), today) for g in goals]


def _current(db: Session, goal: Goal) -> int:
    return (
        goal_repository.contribution_totals(db, [goal.id]).get(goal.id, ContributionTotals()).total
    )


def list_goals(db: Session, today: date, status: str | None = None) -> GoalList:
    goals = goal_repository.list_goals(db, statuses=[status] if status else None)
    items = _reads(db, goals, today)
    return GoalList(
        items=items,
        total_suggested_monthly_saving=sum(
            g.suggested_monthly_saving for g in items if g.status == "active"
        ),
    )


def list_goal_status(db: Session, today: date) -> list[GoalRead]:
    """Goal active (theo priority) kèm số liệu tính sẵn — nguồn của tool Coach `get_goals`."""
    return _reads(db, goal_repository.list_goals(db, statuses=["active"]), today)


def get_goal(db: Session, goal_id: uuid.UUID) -> Goal:
    goal = goal_repository.get(db, goal_id)
    if goal is None:
        raise NotFoundError("Không tìm thấy mục tiêu", "goal_not_found")
    return goal


def get_goal_read(db: Session, goal_id: uuid.UUID, today: date) -> GoalRead:
    return _reads(db, [get_goal(db, goal_id)], today)[0]


def _income_brief(tx: Transaction) -> IncomeBrief:
    return IncomeBrief(
        id=tx.id,
        amount=tx.amount,
        occurred_on=tx.occurred_on,
        note=tx.note,
        category_name=tx.category.name,
    )


def _contribution_read(c: GoalContribution) -> GoalContributionRead:
    tx = c.income_transaction
    return GoalContributionRead(
        id=c.id,
        goal_id=c.goal_id,
        amount=c.amount,
        contributed_on=c.contributed_on,
        income_transaction_id=c.income_transaction_id,
        income_transaction=_income_brief(tx) if tx is not None else None,
        created_at=c.created_at,
    )


def get_goal_detail(db: Session, goal_id: uuid.UUID, today: date) -> GoalDetail:
    goal = get_goal(db, goal_id)
    return GoalDetail(
        goal=_reads(db, [goal], today)[0],
        contributions=[
            _contribution_read(c) for c in goal_repository.list_contributions(db, goal.id)
        ],
    )


# ---------- ghi goal ----------


def _check_deadline(deadline: date, today: date) -> None:
    if deadline < today:
        raise DomainError("Hạn mục tiêu không được ở quá khứ", "deadline_in_past")


def _sync_achieved(goal: Goal, current: int) -> None:
    """active đủ tiền → achieved; achieved thiếu tiền (xoá khoản góp / tăng target) → active."""
    if goal.status == "active" and current >= goal.target_amount:
        goal.status = "achieved"
    elif goal.status == "achieved" and current < goal.target_amount:
        goal.status = "active"


def create_goal(db: Session, data: GoalCreate, today: date) -> GoalRead:
    _check_deadline(data.deadline, today)
    goal = goal_repository.add(
        db,
        Goal(
            name=data.name,
            target_amount=data.target_amount,
            deadline=data.deadline,
            priority=data.priority,
            status="active",
        ),
    )
    db.commit()
    db.refresh(goal)
    return _reads(db, [goal], today)[0]


def update_goal(db: Session, goal_id: uuid.UUID, data: GoalUpdate, today: date) -> GoalRead:
    goal = get_goal(db, goal_id)
    changes = data.model_dump(exclude_unset=True)
    current = _current(db, goal)
    if "deadline" in changes and changes["deadline"] != goal.deadline:
        _check_deadline(changes["deadline"], today)
    if "target_amount" in changes and changes["target_amount"] < current:
        raise DomainError(
            f"Mục tiêu đã có {format_vnd(current)}, số tiền mục tiêu không được nhỏ hơn",
            "target_below_current",
        )
    for field in ("name", "target_amount", "deadline", "priority", "status"):
        if field in changes:
            setattr(goal, field, changes[field])
    if "status" not in changes and "target_amount" in changes:
        _sync_achieved(goal, current)
    db.commit()
    db.refresh(goal)
    return _reads(db, [goal], today)[0]


def delete_goal(db: Session, goal_id: uuid.UUID) -> None:
    """Xoá được goal chưa có khoản góp, hoặc goal đã tạm dừng (xoá luôn lịch sử góp)."""
    goal = get_goal(db, goal_id)
    if goal.status != "paused" and _current(db, goal) > 0:
        raise ConflictError(
            "Mục tiêu đã có khoản góp — hãy tạm dừng mục tiêu trước nếu muốn xoá",
            "goal_has_contributions",
        )
    goal_repository.delete(db, goal)
    db.commit()


def _check_contribution(goal: Goal, amount: int, current: int) -> None:
    if goal.status != "active":
        raise DomainError(
            f"Mục tiêu “{goal.name}” không ở trạng thái đang thực hiện", "goal_not_active"
        )
    remaining = max(0, goal.target_amount - current)
    if amount > remaining:
        raise DomainError(
            f"Mục tiêu “{goal.name}” chỉ còn thiếu {format_vnd(remaining)}",
            "allocation_exceeds_remaining",
        )


def add_contribution(
    db: Session, goal_id: uuid.UUID, data: GoalContributionCreate, today: date
) -> GoalContributionRead:
    goal = get_goal(db, goal_id)
    contributed_on = data.contributed_on or today
    if contributed_on > today:
        raise DomainError("Ngày góp không được ở tương lai", "contribution_in_future")
    current = _current(db, goal)
    _check_contribution(goal, data.amount, current)
    contribution = goal_repository.add_contribution(
        db, GoalContribution(goal_id=goal.id, amount=data.amount, contributed_on=contributed_on)
    )
    _sync_achieved(goal, current + data.amount)
    db.commit()
    db.refresh(contribution)
    return _contribution_read(contribution)


def delete_contribution(db: Session, goal_id: uuid.UUID, contribution_id: uuid.UUID) -> None:
    goal = get_goal(db, goal_id)
    contribution = goal_repository.get_contribution(db, contribution_id)
    if contribution is None or contribution.goal_id != goal.id:
        raise NotFoundError("Không tìm thấy khoản góp", "goal_contribution_not_found")
    goal_repository.delete_contribution(db, contribution)
    _sync_achieved(goal, _current(db, goal))
    db.commit()


# ---------- Pay Yourself First ----------


def _get_income(db: Session, transaction_id: uuid.UUID) -> Transaction:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise DomainError("Không tìm thấy giao dịch thu nhập", "income_transaction_not_found")
    if tx.direction != "income":
        raise DomainError(
            "Chỉ phân bổ được từ giao dịch thu nhập (giao dịch này là khoản chi)",
            "transaction_not_income",
        )
    return tx


def _ensure_unallocated(db: Session, tx: Transaction) -> None:
    allocated = goal_repository.allocated_total_for_income(db, tx.id)
    if allocated > 0:
        raise ConflictError(
            f"Thu nhập này đã được phân bổ {format_vnd(allocated)} cho mục tiêu",
            "income_already_allocated",
        )


def _resolve_items(db: Session, items: Iterable[PyfAllocationItemInput]) -> dict[uuid.UUID, int]:
    """`{goal_id: amount}`; goal phải tồn tại, đang thực hiện, không lặp."""
    amounts: dict[uuid.UUID, int] = {}
    for item in items:
        if item.goal_id in amounts:
            raise DomainError("Mỗi mục tiêu chỉ xuất hiện một lần", "duplicate_goal")
        goal = goal_repository.get(db, item.goal_id)
        if goal is None:
            raise DomainError("Không tìm thấy mục tiêu", "goal_not_found")
        if goal.status != "active":
            raise DomainError(
                f"Mục tiêu “{goal.name}” không ở trạng thái đang thực hiện", "goal_not_active"
            )
        amounts[item.goal_id] = item.amount
    return amounts


def _month_budget(db: Session, day: date) -> Budget | None:
    return budget_repository.get_by_month(db, month_range(day)[0])


def _build_proposal(
    db: Session,
    income: Transaction,
    today: date,
    overrides: dict[uuid.UUID, int] | None = None,
    budget_savings_override: int | None = None,
) -> PyfProposal:
    goals = _reads(db, goal_repository.list_goals(db, statuses=["active"]), today)
    budget = _month_budget(db, income.occurred_on)
    savings_target = (budget.savings_target or 0) if budget is not None else None
    proposed, default_savings = plan_allocation(
        income.amount,
        [(g.suggested_monthly_saving, g.remaining_amount) for g in goals],
        savings_target,
    )
    amounts = proposed if overrides is None else [overrides.get(g.id, 0) for g in goals]
    goal_total = sum(amounts)
    if overrides is not None:
        default_savings = max(0, min(savings_target or 0, income.amount - goal_total))
    budget_savings = (
        budget_savings_override if budget_savings_override is not None else default_savings
    )

    items = []
    warnings = []
    for goal, suggested_amount, amount in zip(goals, proposed, amounts, strict=True):
        exceeds = amount > goal.remaining_amount
        if exceeds:
            warnings.append(
                PyfWarning(
                    code="allocation_exceeds_remaining",
                    message=f"“{goal.name}” chỉ còn thiếu {format_vnd(goal.remaining_amount)}",
                    amount=amount - goal.remaining_amount,
                )
            )
        items.append(
            PyfProposalItem(
                goal_id=goal.id,
                name=goal.name,
                priority=goal.priority,
                deadline=goal.deadline,
                months_remaining=goal.months_remaining,
                current_amount=goal.current_amount,
                remaining_amount=goal.remaining_amount,
                suggested_monthly_saving=goal.suggested_monthly_saving,
                proposed_amount=suggested_amount,
                amount=amount,
                remaining_after=goal.remaining_amount - amount,
                exceeds_remaining=exceeds,
            )
        )
    allocated = goal_total + budget_savings
    if allocated > income.amount:
        warnings.append(
            PyfWarning(
                code="allocation_exceeds_income",
                message=f"Tổng phân bổ {format_vnd(allocated)} lớn hơn thu nhập "
                f"{format_vnd(income.amount)}",
                amount=allocated - income.amount,
            )
        )
    return PyfProposal(
        income_transaction_id=income.id,
        income=_income_brief(income),
        income_amount=income.amount,
        budget_month=month_range(income.occurred_on)[0],
        budget_id=budget.id if budget is not None else None,
        budget_strategy=budget.strategy if budget is not None else None,  # type: ignore[arg-type]
        budget_status=budget.status if budget is not None else None,  # type: ignore[arg-type]
        budget_savings_target=savings_target,
        items=items,
        goal_total=goal_total,
        budget_savings_amount=budget_savings,
        allocated_total=allocated,
        available_spending=income.amount - allocated,
        warnings=warnings,
        valid=not warnings,
    )


def propose_pyf_allocation(db: Session, data: PyfProposalRequest, today: date) -> PyfProposal:
    """Đề xuất (hoặc tính lại với số user đã chỉnh) — không ghi DB."""
    income = _get_income(db, data.income_transaction_id)
    _ensure_unallocated(db, income)
    overrides = _resolve_items(db, data.items) if data.items is not None else None
    return _build_proposal(db, income, today, overrides, data.budget_savings_amount)


def proposal_for_new_income(db: Session, tx: Transaction, today: date) -> PyfProposal | None:
    """Đề xuất gắn vào response `POST /transactions`: chỉ với thu nhập, khi có goal active hoặc
    ngân sách tháng dùng strategy `pyf`."""
    if tx.direction != "income":
        return None
    budget = _month_budget(db, tx.occurred_on)
    if not goal_repository.has_active_goals(db) and (budget is None or budget.strategy != "pyf"):
        return None
    return _build_proposal(db, tx, today)


def confirm_allocations(
    db: Session, data: PyfAllocationRequest, today: date
) -> PyfAllocationResult:
    """User xác nhận: tạo `goal_contributions` gắn thu nhập (1 commit, không ghi một phần)."""
    income = _get_income(db, data.income_transaction_id)
    _ensure_unallocated(db, income)
    amounts = _resolve_items(db, data.items)
    goal_total = sum(amounts.values())
    allocated = goal_total + data.budget_savings_amount
    if allocated > income.amount:
        raise DomainError(
            f"Tổng phân bổ {format_vnd(allocated)} lớn hơn thu nhập {format_vnd(income.amount)}",
            "allocation_exceeds_income",
        )
    goals = {gid: get_goal(db, gid) for gid, amount in amounts.items() if amount > 0}
    totals = goal_repository.contribution_totals(db, list(goals))
    for gid, goal in goals.items():
        _check_contribution(goal, amounts[gid], totals.get(gid, ContributionTotals()).total)

    contributions = []
    for gid, goal in goals.items():
        contributions.append(
            goal_repository.add_contribution(
                db,
                GoalContribution(
                    goal_id=gid,
                    income_transaction_id=income.id,
                    amount=amounts[gid],
                    contributed_on=income.occurred_on,
                ),
            )
        )
        _sync_achieved(goal, totals.get(gid, ContributionTotals()).total + amounts[gid])
    db.commit()
    for c in contributions:
        db.refresh(c)
    return PyfAllocationResult(
        income_transaction_id=income.id,
        income_amount=income.amount,
        contributions=[_contribution_read(c) for c in contributions],
        goal_total=goal_total,
        budget_savings_amount=data.budget_savings_amount,
        available_spending=income.amount - allocated,
        goals=_reads(db, list(goals.values()), today),
    )


def list_unallocated_incomes(db: Session, today: date) -> UnallocatedIncomeList:
    """Thu nhập từ đầu tháng trước tới hôm nay chưa có khoản góp (nút "Phân bổ từ thu nhập")."""
    date_from = add_months(month_range(today)[0], -UNALLOCATED_LOOKBACK_MONTHS)
    incomes = goal_repository.unallocated_incomes(db, date_from, today, limit=UNALLOCATED_LIMIT)
    return UnallocatedIncomeList(items=[_income_brief(tx) for tx in incomes])


# ---------- Coach tool ----------


def get_goals_overview(db: Session, today: date) -> GetGoalsOutput:
    """Output tool read-only `get_goals` (Financial Coach)."""
    goals = list_goal_status(db, today)
    counts = {s: 0 for s in ("paused", "achieved")}
    for g in goal_repository.list_goals(db, statuses=list(counts)):
        counts[g.status] += 1
    return GetGoalsOutput(
        active_goals=[
            GoalToolItem(
                goal_id=g.id,
                name=g.name,
                target_amount=g.target_amount,
                current_amount=g.current_amount,
                remaining_amount=g.remaining_amount,
                progress_pct=g.progress_pct,
                deadline=g.deadline,
                months_remaining=g.months_remaining,
                suggested_monthly_saving=g.suggested_monthly_saving,
                on_track=g.on_track,
                overdue=g.overdue,
                priority=g.priority,
            )
            for g in goals
        ],
        total_suggested_monthly_saving=sum(g.suggested_monthly_saving for g in goals),
        paused_count=counts["paused"],
        achieved_count=counts["achieved"],
        note=None if goals else "Chưa có mục tiêu đang thực hiện — user có thể tạo ở /goals.",
    )
