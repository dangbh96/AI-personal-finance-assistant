"""What-if simulator (Phase 17) — deterministic, **không ghi** giao dịch / ngân sách / mục tiêu.

Mức nền (`build_snapshot`, chỉ đọc DB): trung bình / tháng của `baseline_months` tháng đã trọn
gần nhất trước tháng của `start_date` — thu nhập và chi tiêu theo (danh mục, loại chi tiêu), mặc
định bỏ khoản `irregular` (một lần); mục tiêu đang thực hiện (còn thiếu, hạn, priority); ngân sách
active / closed của tháng `start_date`.

Hàm thuần (unit test không cần DB / AI):
- `apply_params(snapshot, params)` áp lần lượt từng tham số (theo thứ tự gửi lên).
- `compute_goal_completion(remaining, monthly_savings)` → số tháng (2 chữ số) và số ngày
  (1 tháng = 30 ngày, làm tròn lên): 22.000.000 / 4.400.000 → 5,0 tháng = 150 ngày.
- `goal_impacts`: tiết kiệm / tháng dồn cho mục tiêu theo priority (xong mục tiêu 1 mới tới 2).
- `compute_budget_variance`: chi trung bình / tháng của từng dòng ngân sách trước / sau kịch bản.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models import Scenario
from app.repositories import (
    budget_repository,
    category_repository,
    goal_repository,
    scenario_repository,
    transaction_repository,
)
from app.schemas.coach import SimulateGoalItem, SimulateInput, SimulateOutput
from app.schemas.simulator import (
    AddRecurringExpenseParam,
    AppliedParam,
    BudgetVarianceImpact,
    ChangeGoalDeadlineParam,
    ChangeIncomeParam,
    GoalImpact,
    ReduceCategoryParam,
    ScenarioCreate,
    ScenarioList,
    ScenarioParam,
    ScenarioRead,
    SimulationCategoryChange,
    SimulationOptions,
    SimulationRequest,
    SimulationResult,
)
from app.services import budget_service, goal_service
from app.services.money import add_months, format_vnd, round_vnd

DAYS_PER_MONTH = 30
TRACKED_BUDGET_STATUSES = ("active", "closed")


# ---------- dữ liệu đầu vào ----------


@dataclass(frozen=True)
class ExpenseRow:
    category_id: uuid.UUID | None
    category_name: str
    spending_type: str | None
    amount: int  # đồng / tháng


@dataclass(frozen=True)
class GoalState:
    goal_id: uuid.UUID
    name: str
    priority: int
    remaining: int
    deadline: date


@dataclass(frozen=True)
class BudgetLine:
    label: str
    planned: int
    category_ids: frozenset[uuid.UUID] = frozenset()
    spending_types: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CategoryInfo:
    name: str
    kind: str
    default_spending_type: str | None


@dataclass(frozen=True)
class BaselineSnapshot:
    start_date: date
    baseline_from: date
    baseline_to: date
    months: int
    include_irregular: bool
    income: int
    rows: tuple[ExpenseRow, ...]
    goals: tuple[GoalState, ...] = ()
    budget_month: date | None = None
    budget_lines: tuple[BudgetLine, ...] = ()
    categories: dict[uuid.UUID, CategoryInfo] = field(default_factory=dict)

    @property
    def expense(self) -> int:
        return sum(r.amount for r in self.rows)


@dataclass(frozen=True)
class ProjectedSnapshot:
    income: int
    rows: tuple[ExpenseRow, ...]
    goals: tuple[GoalState, ...]
    applied: list[AppliedParam]
    warnings: list[str]

    @property
    def expense(self) -> int:
        return sum(r.amount for r in self.rows)


# ---------- hàm thuần ----------


def percent_of(amount: int, percent: int) -> int:
    return round_vnd(Fraction(amount * percent, 100))


def apply_params(snapshot: BaselineSnapshot, params: Sequence[ScenarioParam]) -> ProjectedSnapshot:
    """Áp tham số theo thứ tự; tham số sau tính trên kết quả của tham số trước."""
    income = snapshot.income
    rows = list(snapshot.rows)
    goals = {g.goal_id: g for g in snapshot.goals}
    applied: list[AppliedParam] = []
    warnings: list[str] = []

    for index, param in enumerate(params):
        if isinstance(param, ReduceCategoryParam):
            info = snapshot.categories.get(param.category_id)
            name = info.name if info else "danh mục"
            reduction = 0
            for i, row in enumerate(rows):
                if row.category_id == param.category_id:
                    cut = percent_of(row.amount, param.percent)
                    rows[i] = replace(row, amount=row.amount - cut)
                    reduction += cut
            if reduction == 0:
                warnings.append(
                    f"“{name}” không có chi tiêu trong mức nền nên giảm {param.percent}% "
                    "không đổi kết quả."
                )
            applied.append(
                AppliedParam(
                    index=index,
                    type=param.type,
                    label=f"Giảm {name} {param.percent}%",
                    percent=param.percent,
                    amount=reduction,
                    delta_monthly_savings=reduction,
                )
            )
        elif isinstance(param, ChangeIncomeParam):
            new_income = max(0, income + param.delta_amount)
            if income + param.delta_amount < 0:
                warnings.append("Thu nhập sau kịch bản không thể âm — tính là 0.")
            delta = new_income - income
            income = new_income
            verb = "tăng" if param.delta_amount >= 0 else "giảm"
            applied.append(
                AppliedParam(
                    index=index,
                    type=param.type,
                    label=f"Thu nhập {verb} {format_vnd(abs(param.delta_amount))}/tháng",
                    amount=param.delta_amount,
                    delta_monthly_savings=delta,
                )
            )
        elif isinstance(param, AddRecurringExpenseParam):
            info = snapshot.categories.get(param.category_id)
            rows.append(
                ExpenseRow(
                    category_id=param.category_id,
                    category_name=info.name if info else "Khác",
                    spending_type=info.default_spending_type if info else None,
                    amount=param.amount,
                )
            )
            applied.append(
                AppliedParam(
                    index=index,
                    type=param.type,
                    label=f"Thêm khoản định kỳ “{param.name}” {format_vnd(param.amount)}/tháng",
                    amount=param.amount,
                    delta_monthly_savings=-param.amount,
                )
            )
        elif isinstance(param, ChangeGoalDeadlineParam):
            goal = goals.get(param.goal_id)
            name = goal.name if goal else "mục tiêu"
            if goal is not None:
                goals[param.goal_id] = replace(goal, deadline=param.new_deadline)
            applied.append(
                AppliedParam(
                    index=index,
                    type=param.type,
                    label=f"Đổi hạn “{name}” sang {param.new_deadline:%d/%m/%Y}",
                    delta_monthly_savings=0,
                )
            )

    projected_rows = tuple(rows)
    savings = income - sum(r.amount for r in projected_rows)
    if savings < 0:
        warnings.append(
            f"Theo kịch bản, chi tiêu cao hơn thu nhập {format_vnd(-savings)} mỗi tháng — "
            "mục tiêu sẽ không tiến triển."
        )
    return ProjectedSnapshot(
        income=income,
        rows=projected_rows,
        goals=tuple(goals[g.goal_id] for g in snapshot.goals),
        applied=applied,
        warnings=warnings,
    )


@dataclass(frozen=True)
class GoalCompletion:
    months: float | None
    days: int | None


def compute_goal_completion(remaining: int, monthly_savings: int) -> GoalCompletion:
    """Số tháng (2 chữ số, nửa làm tròn lên) và số ngày (×30, làm tròn lên) để để dành đủ
    `remaining` với `monthly_savings` / tháng. Không để dành được (≤ 0) → `None`."""
    if remaining <= 0:
        return GoalCompletion(0.0, 0)
    if monthly_savings <= 0:
        return GoalCompletion(None, None)
    months = (Decimal(remaining) / Decimal(monthly_savings)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    days = -(-remaining * DAYS_PER_MONTH // monthly_savings)
    return GoalCompletion(float(months), days)


def completion_date(start: date, days: int | None) -> date | None:
    return start + timedelta(days=days) if days is not None else None


def required_monthly(remaining: int, start: date, deadline: date) -> int:
    """Cần để dành / tháng để kịp hạn — cùng công thức gợi ý của trang Mục tiêu (Phase 11)."""
    return goal_service.suggested_monthly_saving(
        remaining, goal_service.months_remaining(start, deadline)
    )


def goal_impacts(
    before: Sequence[GoalState],
    after: Sequence[GoalState],
    savings_before: int,
    savings_after: int,
    start: date,
) -> list[GoalImpact]:
    """Tiết kiệm / tháng dồn cho mục tiêu theo priority: mục tiêu thứ i đạt khi đủ tổng phần còn
    thiếu của mục tiêu 1..i."""
    after_by_id = {g.goal_id: g for g in after}
    impacts = []
    cumulative = 0
    for goal in sorted(before, key=lambda g: g.priority):
        cumulative += goal.remaining
        new = after_by_id.get(goal.goal_id, goal)
        b = compute_goal_completion(cumulative, savings_before)
        a = compute_goal_completion(cumulative, savings_after)
        date_b = completion_date(start, b.days)
        date_a = completion_date(start, a.days)
        impacts.append(
            GoalImpact(
                goal_id=goal.goal_id,
                name=goal.name,
                priority=goal.priority,
                remaining_amount=goal.remaining,
                deadline_before=goal.deadline,
                deadline_after=new.deadline,
                months_before=b.months,
                months_after=a.months,
                days_before=b.days,
                days_after=a.days,
                completion_date_before=date_b,
                completion_date_after=date_a,
                days_earlier=(b.days - a.days)
                if b.days is not None and a.days is not None
                else None,
                required_monthly_before=required_monthly(goal.remaining, start, goal.deadline),
                required_monthly_after=required_monthly(goal.remaining, start, new.deadline),
                on_track_before=date_b is not None and date_b <= goal.deadline,
                on_track_after=date_a is not None and date_a <= new.deadline,
            )
        )
    return impacts


def _scope_total(rows: Iterable[ExpenseRow], line: BudgetLine) -> int:
    return sum(
        r.amount
        for r in rows
        if (r.category_id is not None and r.category_id in line.category_ids)
        or (r.spending_type is not None and r.spending_type in line.spending_types)
    )


def compute_budget_variance(
    lines: Sequence[BudgetLine],
    rows_before: Sequence[ExpenseRow],
    rows_after: Sequence[ExpenseRow],
) -> list[BudgetVarianceImpact]:
    out = []
    for line in lines:
        before = _scope_total(rows_before, line)
        after = _scope_total(rows_after, line)
        out.append(
            BudgetVarianceImpact(
                label=line.label,
                planned=line.planned,
                baseline_actual=before,
                projected_actual=after,
                variance_before=before - line.planned,
                variance_after=after - line.planned,
            )
        )
    return out


def category_changes(
    rows_before: Sequence[ExpenseRow], rows_after: Sequence[ExpenseRow]
) -> list[SimulationCategoryChange]:
    def totals(rows: Sequence[ExpenseRow]) -> dict[tuple[uuid.UUID | None, str], int]:
        out: dict[tuple[uuid.UUID | None, str], int] = {}
        for r in rows:
            key = (r.category_id, r.category_name)
            out[key] = out.get(key, 0) + r.amount
        return out

    before, after = totals(rows_before), totals(rows_after)
    changes = [
        SimulationCategoryChange(
            category_id=key[0],
            name=key[1],
            baseline=before.get(key, 0),
            projected=after.get(key, 0),
            delta=after.get(key, 0) - before.get(key, 0),
        )
        for key in dict.fromkeys([*before, *after])
        if before.get(key, 0) != after.get(key, 0)
    ]
    return sorted(changes, key=lambda c: (c.delta, c.name))


def simulate(snapshot: BaselineSnapshot, params: Sequence[ScenarioParam]) -> SimulationResult:
    """Kết quả mô phỏng từ mức nền + tham số (hàm thuần)."""
    projected = apply_params(snapshot, params)
    savings_before = snapshot.income - snapshot.expense
    savings_after = projected.income - projected.expense
    warnings = list(projected.warnings)
    if snapshot.income == 0:
        warnings.insert(
            0,
            f"Chưa có thu nhập trong {snapshot.months} tháng mức nền — tiết kiệm / tháng đang "
            "tính từ thu nhập 0.",
        )
    if not snapshot.goals:
        warnings.append("Chưa có mục tiêu đang thực hiện nên không tính ngày hoàn thành.")
    if snapshot.budget_month is None:
        warnings.append(
            f"Tháng {snapshot.start_date:%m/%Y} chưa có ngân sách đang theo dõi — bỏ qua so sánh "
            "ngân sách."
        )
    return SimulationResult(
        start_date=snapshot.start_date,
        baseline_from=snapshot.baseline_from,
        baseline_to=snapshot.baseline_to,
        baseline_months=snapshot.months,
        include_irregular=snapshot.include_irregular,
        baseline_monthly_income=snapshot.income,
        projected_monthly_income=projected.income,
        baseline_monthly_expense=snapshot.expense,
        projected_monthly_expense=projected.expense,
        baseline_monthly_savings=savings_before,
        projected_monthly_savings=savings_after,
        delta_monthly_savings=savings_after - savings_before,
        applied=projected.applied,
        category_changes=category_changes(snapshot.rows, projected.rows),
        goal_impacts=goal_impacts(
            snapshot.goals, projected.goals, savings_before, savings_after, snapshot.start_date
        ),
        budget_month=snapshot.budget_month,
        budget_variance_after=compute_budget_variance(
            snapshot.budget_lines, snapshot.rows, projected.rows
        ),
        warnings=warnings,
    )


# ---------- mức nền từ DB (chỉ đọc) ----------


def baseline_period(start: date, months: int) -> tuple[date, date]:
    first_of_month = start.replace(day=1)
    return add_months(first_of_month, -months), first_of_month - timedelta(days=1)


def _budget_lines(db: Session, start: date) -> tuple[date | None, tuple[BudgetLine, ...]]:
    budget = budget_repository.get_by_month(db, start.replace(day=1))
    if budget is None or budget.status not in TRACKED_BUDGET_STATUSES:
        return None, ()
    jar_categories = (
        {
            name: [c.id for c in cats]
            for name, cats in budget_service.load_jar_categories(db).items()
        }
        if budget.strategy == "envelope"
        else {}
    )
    lines = []
    for allocation in sorted(budget.allocations, key=lambda a: a.position):
        if allocation.group == "savings":
            continue
        scope = budget_service.allocation_scope(budget.strategy, allocation, jar_categories)
        lines.append(
            BudgetLine(
                label=budget_service.allocation_label(
                    allocation.category.name if allocation.category else None,
                    allocation.jar_name,
                ),
                planned=allocation.planned_amount,
                category_ids=scope.category_ids,
                spending_types=scope.spending_types,
            )
        )
    return budget.period_month, tuple(lines)


def build_snapshot(
    db: Session, *, start_date: date, months: int = 3, include_irregular: bool = False
) -> BaselineSnapshot:
    date_from, date_to = baseline_period(start_date, months)
    categories = {
        c.id: CategoryInfo(c.name, c.kind, c.default_spending_type)
        for c in category_repository.list_categories(db, include_archived=True)
    }
    income_total = transaction_repository.totals_by_direction(db, date_from, date_to).get(
        "income", 0
    )
    rows = []
    for (
        category_id,
        spending_type,
        total,
        _count,
    ) in transaction_repository.expense_totals_by_category_and_spending_type(
        db, date_from, date_to
    ):
        if spending_type == "irregular" and not include_irregular:
            continue
        info = categories.get(category_id)
        rows.append(
            ExpenseRow(
                category_id=category_id,
                category_name=info.name if info else "Khác",
                spending_type=spending_type,
                amount=round_vnd(Fraction(total, months)),
            )
        )
    rows.sort(key=lambda r: (-r.amount, r.category_name, r.spending_type or ""))

    active = goal_repository.list_goals(db, statuses=["active"])
    totals = goal_repository.contribution_totals(db, [g.id for g in active])
    goals = tuple(
        GoalState(
            goal_id=g.id,
            name=g.name,
            priority=g.priority,
            remaining=max(0, g.target_amount - (totals[g.id].total if g.id in totals else 0)),
            deadline=g.deadline,
        )
        for g in active
    )
    budget_month, lines = _budget_lines(db, start_date)
    return BaselineSnapshot(
        start_date=start_date,
        baseline_from=date_from,
        baseline_to=date_to,
        months=months,
        include_irregular=include_irregular,
        income=round_vnd(Fraction(income_total, months)),
        rows=tuple(rows),
        goals=goals,
        budget_month=budget_month,
        budget_lines=lines,
        categories=categories,
    )


def _validate_params(snapshot: BaselineSnapshot, params: Sequence[ScenarioParam]) -> None:
    goal_ids = {g.goal_id for g in snapshot.goals}
    for i, param in enumerate(params, start=1):
        if isinstance(param, ReduceCategoryParam | AddRecurringExpenseParam):
            info = snapshot.categories.get(param.category_id)
            if info is None:
                raise DomainError(f"Tham số {i}: danh mục không tồn tại", "category_not_found")
            if info.kind != "expense":
                raise DomainError(
                    f"Tham số {i}: “{info.name}” không phải danh mục chi", "category_kind_mismatch"
                )
        elif isinstance(param, ChangeGoalDeadlineParam):
            if param.goal_id not in goal_ids:
                raise DomainError(
                    f"Tham số {i}: mục tiêu không tồn tại hoặc không đang thực hiện",
                    "goal_not_active",
                )
            if param.new_deadline <= snapshot.start_date:
                raise DomainError(
                    f"Tham số {i}: hạn mới phải sau ngày bắt đầu mô phỏng", "invalid_deadline"
                )
        elif isinstance(param, ChangeIncomeParam) and param.delta_amount == 0:
            raise DomainError(f"Tham số {i}: mức thay đổi thu nhập phải khác 0", "zero_delta")


def run_simulation(
    db: Session, options: SimulationOptions, *, start_date: date
) -> SimulationResult:
    """Đọc mức nền rồi mô phỏng — không ghi DB."""
    snapshot = build_snapshot(
        db,
        start_date=start_date,
        months=options.baseline_months,
        include_irregular=options.include_irregular,
    )
    _validate_params(snapshot, options.params)
    return simulate(snapshot, options.params)


def request_start(request: SimulationRequest | ScenarioCreate, today: date) -> date:
    return request.start_date or today


# ---------- kịch bản đã lưu ----------


def _now() -> datetime:
    return datetime.now(UTC)


def scenario_read(scenario: Scenario) -> ScenarioRead:
    return ScenarioRead(
        id=scenario.id,
        name=scenario.name,
        params=SimulationOptions.model_validate(scenario.params),
        result=SimulationResult.model_validate(scenario.result),
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def create_scenario(db: Session, data: ScenarioCreate, today: date) -> ScenarioRead:
    options = SimulationOptions(
        params=data.params,
        baseline_months=data.baseline_months,
        include_irregular=data.include_irregular,
    )
    result = run_simulation(db, options, start_date=request_start(data, today))
    now = _now()
    scenario = Scenario(
        name=data.name,
        params=options.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
    )
    scenario_repository.add(db, scenario)
    db.commit()
    return scenario_read(scenario)


def list_scenarios(db: Session) -> ScenarioList:
    return ScenarioList(items=[scenario_read(s) for s in scenario_repository.list_scenarios(db)])


def delete_scenario(db: Session, scenario_id: uuid.UUID) -> None:
    scenario = scenario_repository.get(db, scenario_id)
    if scenario is None:
        raise NotFoundError("Không tìm thấy kịch bản", "scenario_not_found")
    scenario_repository.delete(db, scenario)
    db.commit()


# ---------- tool Coach `simulate` ----------


def coach_params(db: Session, data: SimulateInput) -> list[ScenarioParam]:
    """Tham số Coach (slug danh mục) → tham số simulator (id)."""
    params: list[ScenarioParam] = []
    if data.reduce_category_slug or data.reduce_percent:
        if not (data.reduce_category_slug and data.reduce_percent):
            raise DomainError(
                "Giảm theo danh mục cần cả reduce_category_slug và reduce_percent",
                "incomplete_param",
            )
        category = category_repository.get_by_slug(db, data.reduce_category_slug)
        if category is None:
            raise DomainError(
                f"Không có danh mục '{data.reduce_category_slug}'", "category_not_found"
            )
        params.append(
            ReduceCategoryParam(
                type="reduce_category", category_id=category.id, percent=data.reduce_percent
            )
        )
    if data.income_delta:
        params.append(ChangeIncomeParam(type="change_income", delta_amount=data.income_delta))
    if data.add_expense_amount:
        slug = data.add_expense_category_slug or "entertainment"
        category = category_repository.get_by_slug(db, slug)
        if category is None:
            raise DomainError(f"Không có danh mục '{slug}'", "category_not_found")
        params.append(
            AddRecurringExpenseParam(
                type="add_recurring_expense",
                name=data.add_expense_name or "Khoản định kỳ mới",
                amount=data.add_expense_amount,
                category_id=category.id,
            )
        )
    if not params:
        raise DomainError(
            "Cần ít nhất một thay đổi (giảm danh mục, đổi thu nhập hoặc thêm khoản chi)",
            "empty_scenario",
        )
    return params


def simulate_for_coach(db: Session, data: SimulateInput, today: date) -> SimulateOutput:
    options = SimulationOptions(params=coach_params(db, data), baseline_months=data.months)
    result = run_simulation(db, options, start_date=today)
    return SimulateOutput(
        start_date=result.start_date,
        baseline_from=result.baseline_from,
        baseline_to=result.baseline_to,
        changes=[a.label for a in result.applied],
        baseline_monthly_savings=result.baseline_monthly_savings,
        projected_monthly_savings=result.projected_monthly_savings,
        delta_monthly_savings=result.delta_monthly_savings,
        goals=[
            SimulateGoalItem(
                name=g.name,
                remaining_amount=g.remaining_amount,
                days_before=g.days_before,
                days_after=g.days_after,
                days_earlier=g.days_earlier,
                completion_date_before=g.completion_date_before,
                completion_date_after=g.completion_date_after,
            )
            for g in result.goal_impacts
        ],
        warnings=result.warnings,
        link="/simulator",
        note="Đây là mô phỏng trên mức trung bình các tháng gần nhất (1 tháng = 30 ngày), "
        "không thay đổi dữ liệu thật.",
    )
