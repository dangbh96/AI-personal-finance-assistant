"""Lịch dòng tiền + dự báo số dư (Phase 12) — lõi deterministic, không gọi AI (ADR-005, ADR-007).

Công thức (phase-12 § 4.2), mọi số là số nguyên đồng:

    projected_balance[d] = opening_balance
                           + thu/chi đã ghi (giao dịch thật) tới d
                           + thu định kỳ đến hạn tới d − chi định kỳ đến hạn tới d
                           − khoản để dành mục tiêu tới d
                           − average_daily_variable_spending × day_index   (start_date: index 1)

- `opening_balance` = `starting_balance` (user tự nhập — app không đoán số dư ngân hàng) + giao
  dịch đã ghi từ `starting_balance_on` tới trước `start_date`.
- Khoản định kỳ: các kỳ của khoản đang bật từ `next_due_on` trở đi nằm trong cửa sổ; kỳ đã quá hạn
  (`next_due_on < start_date`, chưa ghi giao dịch) **không** tính, chỉ liệt kê `overdue_recurring`.
- `average_daily_variable_spending`: chi 30 ngày trước `start_date`, bỏ khoản `irregular`, giao dịch
  đã gắn khoản định kỳ và giao dịch khớp một khoản chi định kỳ đang bật (cùng danh mục, ±10%), chia
  số ngày có lịch sử; < 7 ngày lịch sử → 0; < 30 ngày → `insufficient_history`.
- Để dành mục tiêu 🎯: mỗi tháng vào ngày `goal_saving_day_of_month` (kẹp cuối tháng), mỗi goal
  active một khoản = gợi ý / tháng tính tại đầu tháng của `start_date` (`goal_service`) — tháng đầu
  trừ phần đã góp trong tháng; không trích từ tháng đến hạn; tổng không vượt phần còn thiếu.
- Cảnh báo: ngày đầu tiên `projected_balance < low_balance_threshold`.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.models import RecurringTransaction
from app.repositories import (
    app_setting_repository,
    goal_repository,
    recurring_repository,
    transaction_repository,
)
from app.repositories.goal_repository import ContributionTotals
from app.schemas.forecast import (
    CalendarEvent,
    CalendarMonth,
    ForecastEvent,
    ForecastOutput,
    ForecastPoint,
    ForecastSettings,
    ForecastSettingsUpdate,
    OverdueRecurring,
)
from app.services import goal_service, recurring_service
from app.services.money import add_months, month_range, round_vnd
from app.services.recurring_detection import within_tolerance
from app.services.recurring_schedule import ICON_GOAL, calendar_icon, day_in_month, occurrences

STARTING_BALANCE_KEY = "forecast.starting_balance"
STARTING_BALANCE_ON_KEY = "forecast.starting_balance_on"
THRESHOLD_KEY = "forecast.low_balance_threshold"
GOAL_DAY_KEY = "forecast.goal_saving_day_of_month"
DEFAULT_THRESHOLD = 1_000_000
DEFAULT_GOAL_DAY = 10
VARIABLE_LOOKBACK_DAYS = 30
MIN_VARIABLE_HISTORY_DAYS = 7
MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 90

# ---------- settings ----------


def _int_setting(raw: Any) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _date_setting(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def get_settings(db: Session) -> ForecastSettings:
    """Đọc `app_settings.forecast.*`; thiếu / sai kiểu → mặc định."""
    threshold = _int_setting(app_setting_repository.get_value(db, THRESHOLD_KEY))
    goal_day = _int_setting(app_setting_repository.get_value(db, GOAL_DAY_KEY))
    if threshold is None or threshold < 0:
        threshold = DEFAULT_THRESHOLD
    if goal_day is None or not 1 <= goal_day <= 31:
        goal_day = DEFAULT_GOAL_DAY
    return ForecastSettings(
        starting_balance=_int_setting(app_setting_repository.get_value(db, STARTING_BALANCE_KEY)),
        starting_balance_on=_date_setting(
            app_setting_repository.get_value(db, STARTING_BALANCE_ON_KEY)
        ),
        low_balance_threshold=threshold,
        goal_saving_day_of_month=goal_day,
    )


def update_settings(db: Session, data: ForecastSettingsUpdate, today: date) -> ForecastSettings:
    changes = data.model_dump(exclude_unset=True)
    if "starting_balance" in changes:
        app_setting_repository.set_value(db, STARTING_BALANCE_KEY, changes["starting_balance"])
        if changes["starting_balance"] is None:
            app_setting_repository.set_value(db, STARTING_BALANCE_ON_KEY, None)
        elif "starting_balance_on" not in changes:
            changes["starting_balance_on"] = today
    if changes.get("starting_balance_on") is not None:
        app_setting_repository.set_value(
            db, STARTING_BALANCE_ON_KEY, changes["starting_balance_on"].isoformat()
        )
    if "low_balance_threshold" in changes:
        app_setting_repository.set_value(db, THRESHOLD_KEY, changes["low_balance_threshold"])
    if "goal_saving_day_of_month" in changes:
        app_setting_repository.set_value(db, GOAL_DAY_KEY, changes["goal_saving_day_of_month"])
    db.commit()
    return get_settings(db)


# ---------- hàm thuần ----------


@dataclass(frozen=True)
class CashflowEvent:
    on: date
    kind: str  # recurring | goal_saving
    direction: str
    amount: int
    label: str
    icon: str
    recurring_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ProjectedDay:
    on: date
    projected_balance: int
    delta_income: int
    delta_expense: int
    delta_goal_saving: int
    delta_variable: int
    events: tuple[CashflowEvent, ...] = ()


@dataclass(frozen=True)
class Projection:
    days: list[ProjectedDay]
    low_balance_warning_day: date | None
    min_balance: int
    min_balance_day: date
    end_balance: int


def project_balance(
    opening_balance: int,
    start: date,
    days: int,
    events: Sequence[CashflowEvent],
    average_daily_variable: int,
    threshold: int,
    actual_by_day: Mapping[date, Mapping[str, int]] | None = None,
) -> Projection:
    """Số dư dự báo từng ngày `[start, start + days − 1]` (xem công thức ở đầu module)."""
    if days < 1:
        raise ValueError("days phải ≥ 1")
    by_day: dict[date, list[CashflowEvent]] = {}
    for event in events:
        by_day.setdefault(event.on, []).append(event)
    actual_by_day = actual_by_day or {}

    balance = opening_balance
    result: list[ProjectedDay] = []
    warning: date | None = None
    min_balance, min_day = None, start
    for index in range(days):
        day = start + timedelta(days=index)
        todays = by_day.get(day, [])
        actual = actual_by_day.get(day, {})
        income = actual.get("income", 0) + sum(
            e.amount for e in todays if e.kind == "recurring" and e.direction == "income"
        )
        expense = actual.get("expense", 0) + sum(
            e.amount for e in todays if e.kind == "recurring" and e.direction == "expense"
        )
        goal = sum(e.amount for e in todays if e.kind == "goal_saving")
        balance += income - expense - goal - average_daily_variable
        result.append(
            ProjectedDay(
                on=day,
                projected_balance=balance,
                delta_income=income,
                delta_expense=expense,
                delta_goal_saving=goal,
                delta_variable=average_daily_variable,
                events=tuple(todays),
            )
        )
        if warning is None and balance < threshold:
            warning = day
        if min_balance is None or balance < min_balance:
            min_balance, min_day = balance, day
    assert min_balance is not None
    return Projection(
        days=result,
        low_balance_warning_day=warning,
        min_balance=min_balance,
        min_balance_day=min_day,
        end_balance=balance,
    )


@dataclass(frozen=True)
class GoalPlanInput:
    name: str
    target: int
    current: int
    contributed_in_start_month: int
    deadline: date


def monthly_goal_plan(goal: GoalPlanInput, month_start: date) -> int:
    """Gợi ý / tháng của goal tính tại đầu tháng (trước các khoản góp trong tháng đó)."""
    base = goal.current - goal.contributed_in_start_month
    return goal_service.compute_progress(
        goal.target, base, goal.deadline, month_start
    ).suggested_monthly_saving


def goal_saving_schedule(
    goals: Sequence[GoalPlanInput], start: date, end: date, day_of_month: int
) -> list[tuple[date, int, list[str]]]:
    """Khoản để dành mục tiêu trong `[start, end]`: `(ngày, tổng, tên goal)` mỗi tháng.

    Tháng của `start`: kế hoạch tháng − phần đã góp trong tháng. Tháng sau: kế hoạch tháng, chỉ
    trước tháng đến hạn (goal quá hạn chỉ trích ở tháng đầu). Tổng mỗi goal ≤ phần còn thiếu."""
    first_month = start.replace(day=1)
    plans = [monthly_goal_plan(g, first_month) for g in goals]
    left = [max(0, g.target - g.current) for g in goals]
    result: list[tuple[date, int, list[str]]] = []
    month, index = first_month, 0
    while month <= end:
        due = day_in_month(month.year, month.month, day_of_month)
        in_window = start <= due <= end
        total, names = 0, []
        for i, goal in enumerate(goals):
            if index == 0:
                amount = max(0, plans[i] - goal.contributed_in_start_month)
            elif goal.deadline < first_month or (month.year, month.month) >= (
                goal.deadline.year,
                goal.deadline.month,
            ):
                amount = 0
            else:
                amount = plans[i]
            amount = min(amount, left[i])
            if in_window and amount > 0:
                left[i] -= amount
                total += amount
                names.append(goal.name)
        if in_window and total > 0:
            result.append((due, total, names))
        month, index = add_months(month, 1), index + 1
    return result


def variable_average(total: int, history_days: int) -> int:
    """Trung bình chi biến đổi / ngày (làm tròn tới đồng); < 7 ngày lịch sử → 0."""
    if history_days < MIN_VARIABLE_HISTORY_DAYS:
        return 0
    return round_vnd(Fraction(total, history_days))


# ---------- DB ----------


def _goal_inputs(db: Session, month_start: date) -> list[GoalPlanInput]:
    goals = goal_repository.list_goals(db, statuses=["active"])
    ids = [g.id for g in goals]
    totals = goal_repository.contribution_totals(db, ids)
    in_month = goal_repository.contributed_between(db, ids, *month_range(month_start))
    return [
        GoalPlanInput(
            name=g.name,
            target=g.target_amount,
            current=totals.get(g.id, ContributionTotals()).total,
            contributed_in_start_month=in_month.get(g.id, 0),
            deadline=g.deadline,
        )
        for g in goals
    ]


def _goal_label(names: list[str]) -> str:
    return "Để dành mục tiêu: " + ", ".join(names)


def _recurring_events(
    recurrings: Sequence[RecurringTransaction], start: date, end: date
) -> list[CashflowEvent]:
    events: list[CashflowEvent] = []
    for r in recurrings:
        icon = recurring_service.icon_of(r)
        for day in occurrences(recurring_service.rule_of(r), r.next_due_on, start, end):
            events.append(
                CashflowEvent(
                    on=day,
                    kind="recurring",
                    direction=r.direction,
                    amount=r.amount,
                    label=r.name,
                    icon=icon,
                    recurring_id=r.id,
                )
            )
    return events


def _variable_spending(
    db: Session, start: date, recurrings: Sequence[RecurringTransaction]
) -> tuple[int, int, int]:
    """`(trung bình / ngày, số ngày lịch sử, tổng)` của 30 ngày trước `start`."""
    window_to = start - timedelta(days=1)
    window_from = start - timedelta(days=VARIABLE_LOOKBACK_DAYS)
    earliest = recurring_repository.earliest_transaction_date(db)
    if earliest is None or earliest > window_to:
        return 0, 0, 0
    history_from = max(window_from, earliest)
    history_days = (window_to - history_from).days + 1
    expense_recurrings = [r for r in recurrings if r.direction == "expense"]
    total = 0
    for t in transaction_repository.list_between(db, history_from, window_to):
        if t.direction != "expense" or t.spending_type == "irregular" or t.recurring_id:
            continue
        if any(
            r.category_id == t.category_id and within_tolerance(t.amount, r.amount)
            for r in expense_recurrings
        ):
            continue
        total += t.amount
    return variable_average(total, history_days), history_days, total


def build_forecast(db: Session, start: date, days: int) -> ForecastOutput:
    if not MIN_FORECAST_DAYS <= days <= MAX_FORECAST_DAYS:
        raise ValueError("days ngoài phạm vi")
    settings = get_settings(db)
    end = start + timedelta(days=days - 1)
    starting_balance = settings.starting_balance or 0
    as_of = settings.starting_balance_on if settings.starting_balance is not None else None
    actual_from = as_of or start

    opening = starting_balance
    if actual_from < start:
        totals = transaction_repository.totals_by_direction(
            db, actual_from, start - timedelta(days=1)
        )
        opening += totals.get("income", 0) - totals.get("expense", 0)
    actual_by_day = transaction_repository.daily_totals_by_direction(
        db, max(actual_from, start), end
    )

    recurrings = recurring_service.list_active(db)
    events = _recurring_events(recurrings, start, end)
    goals = _goal_inputs(db, start.replace(day=1))
    for day, amount, names in goal_saving_schedule(
        goals, start, end, settings.goal_saving_day_of_month
    ):
        events.append(
            CashflowEvent(
                on=day,
                kind="goal_saving",
                direction="expense",
                amount=amount,
                label=_goal_label(names),
                icon=ICON_GOAL,
            )
        )
    average, history_days, _ = _variable_spending(db, start, recurrings)
    projection = project_balance(
        opening,
        start,
        days,
        events,
        average,
        settings.low_balance_threshold,
        actual_by_day,
    )
    return ForecastOutput(
        start_date=start,
        days=days,
        starting_balance=starting_balance,
        starting_balance_on=as_of,
        starting_balance_set=settings.starting_balance is not None,
        opening_balance=opening,
        low_balance_threshold=settings.low_balance_threshold,
        points=[
            ForecastPoint(
                date=p.on,
                projected_balance=p.projected_balance,
                delta_income=p.delta_income,
                delta_expense=p.delta_expense,
                delta_goal_saving=p.delta_goal_saving,
                delta_variable=p.delta_variable,
                events=[
                    ForecastEvent(
                        kind=e.kind,  # type: ignore[arg-type]
                        label=e.label,
                        icon=e.icon,
                        direction=e.direction,  # type: ignore[arg-type]
                        amount=e.amount,
                        recurring_id=e.recurring_id,
                    )
                    for e in sorted(p.events, key=_event_order)
                ],
            )
            for p in projection.days
        ],
        low_balance_warning_day=projection.low_balance_warning_day,
        min_balance=projection.min_balance,
        min_balance_day=projection.min_balance_day,
        end_balance=projection.end_balance,
        average_daily_variable_spending=average,
        variable_history_days=history_days,
        insufficient_history=history_days < VARIABLE_LOOKBACK_DAYS,
        monthly_goal_saving=sum(monthly_goal_plan(g, start.replace(day=1)) for g in goals),
        goal_saving_day_of_month=settings.goal_saving_day_of_month,
        recurring_income_total=sum(
            e.amount for e in events if e.kind == "recurring" and e.direction == "income"
        ),
        recurring_expense_total=sum(
            e.amount for e in events if e.kind == "recurring" and e.direction == "expense"
        ),
        goal_saving_total=sum(e.amount for e in events if e.kind == "goal_saving"),
        variable_spending_total=average * days,
        overdue_recurring=[
            OverdueRecurring(
                recurring_id=r.id,
                name=r.name,
                direction=r.direction,  # type: ignore[arg-type]
                amount=r.amount,
                due_on=r.next_due_on,
            )
            for r in recurrings
            if r.next_due_on < start
        ],
    )


_KIND_ORDER = {"paid": 0, "recurring": 1, "goal_saving": 2}


def _event_order(e: CashflowEvent) -> tuple[int, int, int, str]:
    return (_KIND_ORDER[e.kind], 0 if e.direction == "income" else 1, -e.amount, e.label)


def calendar_month(db: Session, month: date, today: date) -> CalendarMonth:
    """Sự kiện của tháng: giao dịch đã ghi từ khoản định kỳ (`paid`), các kỳ sắp tới / quá hạn
    của khoản đang bật (`recurring`), khoản để dành mục tiêu kế hoạch (`goal_saving`, từ tháng
    hiện tại trở đi)."""
    m_start, m_end = month_range(month)
    events: list[CalendarEvent] = []
    for t in recurring_repository.linked_transactions_between(db, m_start, m_end):
        events.append(
            CalendarEvent(
                date=t.occurred_on,
                icon=calendar_icon(t.direction, t.category.slug, t.note),
                label=t.note or t.category.name,
                amount=t.amount,
                direction=t.direction,  # type: ignore[arg-type]
                kind="paid",
                recurring_id=t.recurring_id,
                transaction_id=t.id,
            )
        )
    for e in _recurring_events(recurring_service.list_active(db), m_start, m_end):
        events.append(
            CalendarEvent(
                date=e.on,
                icon=e.icon,
                label=e.label,
                amount=e.amount,
                direction=e.direction,  # type: ignore[arg-type]
                kind="recurring",
                recurring_id=e.recurring_id,
                overdue=e.on < today,
            )
        )
    current_month = today.replace(day=1)
    if m_end >= current_month:
        settings = get_settings(db)
        goals = _goal_inputs(db, current_month)
        for day, amount, names in goal_saving_schedule(
            goals, current_month, m_end, settings.goal_saving_day_of_month
        ):
            if day >= m_start:
                events.append(
                    CalendarEvent(
                        date=day,
                        icon=ICON_GOAL,
                        label=_goal_label(names),
                        amount=amount,
                        direction="expense",
                        kind="goal_saving",
                        overdue=day < today,
                    )
                )
    events.sort(
        key=lambda e: (
            e.date,
            _KIND_ORDER[e.kind],
            0 if e.direction == "income" else 1,
            -e.amount,
            e.label,
        )
    )
    return CalendarMonth(
        month=m_start,
        today=today,
        events=events,
        income_total=sum(e.amount for e in events if e.direction == "income"),
        expense_total=sum(
            e.amount for e in events if e.direction == "expense" and e.kind != "goal_saving"
        ),
        goal_saving_total=sum(e.amount for e in events if e.kind == "goal_saving"),
    )
