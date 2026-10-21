"""Budget adjustment advisor (Phase 8) — gom evidence, lưu advice, accept / dismiss. Deterministic.

Luồng tạo advice (router `budget_advice`): `prepare_advice` (evidence + verdict qua
`advisor_rules`) → `ai/advice_writer` viết explanation (AI hoặc template) → `save_advice`.

- Chỉ tạo cho tháng có budget active / closed; bỏ qua dòng nhóm `savings` (không theo dõi actual).
- Mỗi `(dòng, tháng)` tối đa 1 advice `open`. Dòng đã có advice accepted / dismissed của tháng
  thì không tạo lại (user đã quyết định). Advice `open` chỉ tính lại khi `regenerate`.
- Accept: bắt buộc `confirm = true`, chỉ verdict `adjust_budget` đang `open`; áp dụng
  `proposed_planned_amount` vào budget tháng đích qua `budget_service` (chưa có → tạo nháp copy
  từ tháng của advice) — cùng một commit.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import BudgetAdvice, BudgetAllocation
from app.models.enums import AdviceVerdict
from app.repositories import (
    app_setting_repository,
    budget_advice_repository,
    transaction_repository,
)
from app.schemas.budget import BudgetAllocationRead
from app.schemas.budget_advice import (
    AdviceNarrative,
    AdvisorSettings,
    AdvisorSettingsUpdate,
    AppliedBudgetRead,
    BudgetAdviceAcceptRequest,
    BudgetAdviceAcceptResult,
    BudgetAdviceDismissRequest,
    BudgetAdviceEvidence,
    BudgetAdviceRead,
)
from app.schemas.category import CategoryBrief
from app.services import advice_narrative, advisor_rules, analytics_service, budget_service
from app.services.advisor_rules import AdviceInput, MonthActual, ScopeTransaction, Thresholds
from app.services.money import add_months, month_range

SETTINGS_KEY = "budget_advisor"


# ---------- thresholds ----------


def get_settings(db: Session) -> AdvisorSettings:
    """`app_settings.budget_advisor`, key thiếu / sai kiểu → giá trị mặc định."""
    raw = app_setting_repository.get_value(db, SETTINGS_KEY)
    merged = advisor_rules.DEFAULT_SETTINGS.model_dump()
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in merged:
                continue
            try:
                merged = AdvisorSettings(**{**merged, key: value}).model_dump()
            except ValidationError:
                continue
    return AdvisorSettings(**merged)


def update_settings(db: Session, data: AdvisorSettingsUpdate) -> AdvisorSettings:
    current = get_settings(db).model_dump()
    current.update({k: getattr(data, k) for k in data.model_fields_set})
    try:
        settings = AdvisorSettings(**current)
    except ValidationError as exc:
        raise DomainError(str(exc.errors()[0]["msg"]), "invalid_settings") from exc
    app_setting_repository.set_value(db, SETTINGS_KEY, settings.model_dump())
    db.commit()
    return settings


# ---------- evidence ----------


@dataclass(frozen=True)
class AdviceDraft:
    allocation: BudgetAllocation
    month: date
    verdict: AdviceVerdict
    evidence: BudgetAdviceEvidence
    existing: BudgetAdvice | None


def _ensure_month(month: date, today: date) -> None:
    if month.day != 1:
        raise DomainError("Tháng phải bắt đầu từ ngày 1", "month_not_first_day")
    if month > today:
        raise DomainError("Tháng này chưa bắt đầu — chưa thể tạo tư vấn", "month_not_started")


def _scope_transaction(t) -> ScopeTransaction:
    return ScopeTransaction(
        id=t.id,
        occurred_on=t.occurred_on,
        note=t.note,
        amount=t.amount,
        category_name=t.category.name,
        spending_type=t.spending_type,
    )


def _target_allocations(
    allocations: Sequence[BudgetAllocation], allocation_id: uuid.UUID | None, month: date
) -> list[BudgetAllocation]:
    if allocation_id is None:
        return [a for a in allocations if a.group != "savings"]
    allocation = next((a for a in allocations if a.id == allocation_id), None)
    if allocation is None:
        raise NotFoundError(
            f"Không có dòng phân bổ này trong ngân sách tháng {month:%m/%Y}",
            "allocation_not_found",
        )
    if allocation.group == "savings":
        raise DomainError(
            "Dòng tiết kiệm không theo dõi chi tiêu nên không có tư vấn điều chỉnh",
            "allocation_not_tracked",
        )
    return [allocation]


def compute_evidence(
    db: Session,
    month: date,
    *,
    today: date,
    allocation_id: uuid.UUID | None = None,
    settings: AdvisorSettings | None = None,
) -> list[tuple[BudgetAllocation, advisor_rules.AdviceResult]]:
    """Verdict + evidence cho các dòng (không ghi DB, không AI)."""
    _ensure_month(month, today)
    budget = analytics_service.tracked_budget(db, month)
    allocations = _target_allocations(budget.allocations, allocation_id, month)
    thresholds = Thresholds.from_settings(settings or get_settings(db))
    scope_of = analytics_service.scope_resolver(db, budget)

    months = [add_months(month, -k) for k in range(thresholds.min_history_months - 1, -1, -1)]
    rows = {
        m: transaction_repository.expense_totals_by_category_and_spending_type(db, *month_range(m))
        for m in months
    }
    start, end = month_range(month)
    as_of = min(today, end)
    results = []
    for allocation in allocations:
        scope = scope_of(allocation)
        history = [MonthActual(m, *analytics_service.scope_actual(scope, rows[m])) for m in months]
        transactions = transaction_repository.all_in_scope(
            db, start, end, scope.category_ids, scope.spending_types
        )
        inp = AdviceInput(
            label=budget_service.allocation_label(
                allocation.category.name if allocation.category else None, allocation.jar_name
            ),
            group=allocation.group,
            category_slug=allocation.category.slug if allocation.category else None,
            month=month,
            as_of=as_of,
            month_complete=today >= end,
            planned=allocation.planned_amount,
            actual=history[-1].actual,
            comfort_high=getattr(allocation, "comfort_high", None),
            transactions=[_scope_transaction(t) for t in transactions],
            history=history,
        )
        results.append((allocation, advisor_rules.evaluate(inp, thresholds)))
    return results


def prepare_advice(
    db: Session,
    month: date,
    *,
    today: date,
    allocation_id: uuid.UUID | None = None,
    regenerate: bool = False,
) -> list[AdviceDraft]:
    """Các dòng cần (tính lại) explanation: chưa có advice của tháng, hoặc advice `open` khi
    `regenerate`. Dòng đã accepted / dismissed giữ nguyên."""
    drafts = []
    for allocation, result in compute_evidence(db, month, today=today, allocation_id=allocation_id):
        existing = budget_advice_repository.for_allocation_month(db, allocation.id, month)
        open_advice = next((a for a in existing if a.status == "open"), None)
        if open_advice is None and existing:
            continue
        if open_advice is not None and not regenerate:
            continue
        drafts.append(AdviceDraft(allocation, month, result.verdict, result.evidence, open_advice))
    return drafts


def save_advice(
    db: Session, drafts: Sequence[AdviceDraft], texts: Sequence[tuple[AdviceNarrative, str]]
) -> list[BudgetAdvice]:
    saved = []
    for draft, (narrative, model) in zip(drafts, texts, strict=True):
        advice = draft.existing or BudgetAdvice(
            budget_allocation_id=draft.allocation.id, month=draft.month, status="open"
        )
        advice.verdict = draft.verdict
        advice.evidence = draft.evidence.model_dump(mode="json")
        advice.explanation = advice_narrative.join_text(narrative)
        advice.narrative = narrative.model_dump(mode="json")
        advice.model = model
        if draft.existing is None:
            budget_advice_repository.add(db, advice)
        saved.append(advice)
    db.flush()
    db.commit()
    return saved


# ---------- đọc ----------


def get_advice(db: Session, advice_id: uuid.UUID) -> BudgetAdvice:
    advice = budget_advice_repository.get(db, advice_id)
    if advice is None:
        raise NotFoundError("Không tìm thấy tư vấn này", "advice_not_found")
    return advice


def list_advice(
    db: Session,
    *,
    month: date | None = None,
    status: str | None = None,
    allocation_id: uuid.UUID | None = None,
) -> list[BudgetAdvice]:
    return budget_advice_repository.list_advice(
        db,
        month=month_range(month)[0] if month else None,
        status=status,
        allocation_id=allocation_id,
    )


def to_read(advice: BudgetAdvice) -> BudgetAdviceRead:
    allocation = advice.allocation
    category = allocation.category
    return BudgetAdviceRead(
        id=advice.id,
        budget_allocation_id=allocation.id,
        budget_id=allocation.budget_id,
        month=advice.month,
        allocation_label=budget_service.allocation_label(
            category.name if category else None, allocation.jar_name
        ),
        group=allocation.group,  # type: ignore[arg-type]
        category=CategoryBrief.model_validate(category) if category else None,
        jar_name=allocation.jar_name,
        verdict=advice.verdict,  # type: ignore[arg-type]
        evidence=BudgetAdviceEvidence.model_validate(advice.evidence),
        explanation=advice.explanation,
        narrative=AdviceNarrative.model_validate(advice.narrative) if advice.narrative else None,
        model=advice.model,
        status=advice.status,  # type: ignore[arg-type]
        applied_month=advice.applied_month,
        dismiss_reason=advice.dismiss_reason,
        created_at=advice.created_at,
        updated_at=advice.updated_at,
    )


# ---------- accept / dismiss ----------


def _ensure_open(advice: BudgetAdvice) -> None:
    if advice.status != "open":
        raise ConflictError(
            "Tư vấn này đã được xử lý (đã áp dụng hoặc đã bỏ qua)", "advice_not_open"
        )


def accept_advice(
    db: Session, advice_id: uuid.UUID, data: BudgetAdviceAcceptRequest
) -> BudgetAdviceAcceptResult:
    """User xác nhận → đặt planned mới cho dòng tương ứng ở budget tháng đích."""
    advice = get_advice(db, advice_id)
    if not data.confirm:
        raise DomainError(
            "Cần xác nhận (confirm = true) trước khi áp dụng thay đổi ngân sách",
            "confirmation_required",
        )
    _ensure_open(advice)
    proposed = advice.evidence.get("proposed_planned_amount")
    if advice.verdict != "adjust_budget" or not isinstance(proposed, int):
        raise DomainError(
            "Chỉ áp dụng được tư vấn “Budget có thể thấp hơn thực tế” (adjust_budget)",
            "advice_not_adjustable",
        )
    target = data.target_month or add_months(advice.month, 1)
    if target <= advice.month:
        raise DomainError("Tháng áp dụng phải sau tháng của tư vấn", "invalid_target_month")

    budget, created = budget_service.ensure_next_month_budget(db, target, advice.month)
    allocation = budget_service.set_allocation_planned(
        db, budget, advice.allocation, proposed, confirm_over_income=data.confirm_over_income
    )
    advice.status = "accepted"
    advice.applied_month = target
    db.flush()
    db.commit()
    db.refresh(budget)
    db.refresh(allocation)
    db.refresh(advice)
    return BudgetAdviceAcceptResult(
        advice=to_read(advice),
        updated_allocation=BudgetAllocationRead.model_validate(allocation),
        budget=AppliedBudgetRead(
            id=budget.id,
            period_month=budget.period_month,
            status=budget.status,  # type: ignore[arg-type]
            created=created,
        ),
    )


def dismiss_advice(
    db: Session, advice_id: uuid.UUID, data: BudgetAdviceDismissRequest
) -> BudgetAdvice:
    advice = get_advice(db, advice_id)
    _ensure_open(advice)
    advice.status = "dismissed"
    advice.dismiss_reason = data.reason or None
    db.flush()
    db.commit()
    db.refresh(advice)
    return advice
