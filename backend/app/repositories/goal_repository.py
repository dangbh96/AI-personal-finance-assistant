import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.models import Goal, GoalContribution, Transaction

_STATUS_ORDER = case((Goal.status == "active", 0), (Goal.status == "paused", 1), else_=2)


@dataclass(frozen=True)
class ContributionTotals:
    total: int = 0
    count: int = 0
    last_on: date | None = None


def get(db: Session, goal_id: uuid.UUID) -> Goal | None:
    return db.get(Goal, goal_id)


def list_goals(db: Session, *, statuses: Collection[str] | None = None) -> list[Goal]:
    """Active → paused → achieved; trong nhóm: priority, deadline, ngày tạo."""
    stmt = select(Goal).where(Goal.user_id.is_(None))
    if statuses is not None:
        stmt = stmt.where(Goal.status.in_(list(statuses)))
    stmt = stmt.order_by(_STATUS_ORDER, Goal.priority, Goal.deadline, Goal.created_at, Goal.id)
    return list(db.scalars(stmt))


def has_active_goals(db: Session) -> bool:
    return bool(db.scalar(select(exists().where(Goal.user_id.is_(None), Goal.status == "active"))))


def add(db: Session, goal: Goal) -> Goal:
    db.add(goal)
    db.flush()
    return goal


def delete(db: Session, goal: Goal) -> None:
    db.delete(goal)
    db.flush()


def contribution_totals(
    db: Session, goal_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, ContributionTotals]:
    if not goal_ids:
        return {}
    rows = db.execute(
        select(
            GoalContribution.goal_id,
            func.coalesce(func.sum(GoalContribution.amount), 0),
            func.count(),
            func.max(GoalContribution.contributed_on),
        )
        .where(GoalContribution.goal_id.in_(list(goal_ids)))
        .group_by(GoalContribution.goal_id)
    )
    return {gid: ContributionTotals(int(total), int(n), last) for gid, total, n, last in rows}


def contributed_between(
    db: Session, goal_ids: Collection[uuid.UUID], date_from: date, date_to: date
) -> dict[uuid.UUID, int]:
    """Tổng khoản góp theo goal có `contributed_on` trong `[date_from, date_to]`."""
    if not goal_ids:
        return {}
    rows = db.execute(
        select(GoalContribution.goal_id, func.coalesce(func.sum(GoalContribution.amount), 0))
        .where(
            GoalContribution.goal_id.in_(list(goal_ids)),
            GoalContribution.contributed_on >= date_from,
            GoalContribution.contributed_on <= date_to,
        )
        .group_by(GoalContribution.goal_id)
    )
    return {gid: int(total) for gid, total in rows}


def list_contributions(db: Session, goal_id: uuid.UUID) -> list[GoalContribution]:
    stmt = (
        select(GoalContribution)
        .where(GoalContribution.goal_id == goal_id)
        .order_by(
            GoalContribution.contributed_on.desc(),
            GoalContribution.created_at.desc(),
            GoalContribution.id.desc(),
        )
        # Liên kết thu nhập có thể vừa bị DB đặt NULL (xoá giao dịch) → đọc lại từ DB.
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(stmt))


def get_contribution(db: Session, contribution_id: uuid.UUID) -> GoalContribution | None:
    return db.get(GoalContribution, contribution_id)


def add_contribution(db: Session, contribution: GoalContribution) -> GoalContribution:
    db.add(contribution)
    db.flush()
    return contribution


def delete_contribution(db: Session, contribution: GoalContribution) -> None:
    db.delete(contribution)
    db.flush()


def allocated_total_for_income(db: Session, transaction_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(GoalContribution.amount), 0)).where(
                GoalContribution.income_transaction_id == transaction_id
            )
        )
        or 0
    )


def unallocated_incomes(
    db: Session, date_from: date, date_to: date, *, limit: int
) -> list[Transaction]:
    """Thu nhập trong khoảng ngày chưa có khoản góp goal nào, mới nhất trước."""
    has_contribution = exists().where(GoalContribution.income_transaction_id == Transaction.id)
    stmt = (
        select(Transaction)
        .where(
            Transaction.user_id.is_(None),
            Transaction.direction == "income",
            Transaction.occurred_on >= date_from,
            Transaction.occurred_on <= date_to,
            ~has_contribution,
        )
        .order_by(
            Transaction.occurred_on.desc(), Transaction.created_at.desc(), Transaction.id.desc()
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))
