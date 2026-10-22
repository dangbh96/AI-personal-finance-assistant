"""Truy vấn `scenarios` (Phase 17)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scenario

MAX_LISTED = 50


def get(db: Session, scenario_id: uuid.UUID) -> Scenario | None:
    return db.get(Scenario, scenario_id)


def list_scenarios(db: Session, limit: int = MAX_LISTED) -> list[Scenario]:
    stmt = (
        select(Scenario)
        .where(Scenario.user_id.is_(None))
        .order_by(Scenario.created_at.desc(), Scenario.id)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def add(db: Session, scenario: Scenario) -> Scenario:
    db.add(scenario)
    db.flush()
    return scenario


def delete(db: Session, scenario: Scenario) -> None:
    db.delete(scenario)
    db.flush()
