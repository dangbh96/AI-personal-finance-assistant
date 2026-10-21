"""Khoản định kỳ (Phase 12) — CRUD, phát hiện từ lịch sử, ghi kỳ đến hạn thành giao dịch.

Deterministic, không gọi AI (ADR-005):
- Lịch / `next_due_on`: `services/recurring_schedule` (31 → cuối tháng ngắn, 29/02, weekly ISO).
- Phát hiện: `services/recurring_detection` → **đề xuất** lưu ở `app_settings.recurring.suggestions`
  (kết quả lần phát hiện gần nhất). Chỉ khi user xác nhận mới tạo khoản định kỳ
  (`auto_detected = true`) và gắn các giao dịch lịch sử của mẫu (`transactions.recurring_id`).
  Từ chối → nhớ khoá mẫu ở `app_settings.recurring.dismissed_suggestions` để không đề xuất lại.
- "Tạo giao dịch": giao dịch thật `source = 'recurring'`, `recurring_id` = khoản định kỳ;
  `next_due_on` tiến **một** kỳ (mỗi kỳ bị lỡ vẫn cần user xác nhận riêng). Không có job nền tự
  tạo giao dịch.
"""

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import Category, RecurringTransaction, Transaction
from app.repositories import app_setting_repository, recurring_repository, transaction_repository
from app.schemas.category import CategoryBrief
from app.schemas.recurring import (
    RecurringCreate,
    RecurringDetectRequest,
    RecurringList,
    RecurringRead,
    RecurringSuggestion,
    RecurringSuggestionConfirm,
    RecurringSuggestionList,
    RecurringTransactionCreate,
    RecurringUpdate,
)
from app.services import transaction_service
from app.services.recurring_detection import DetectedPattern, HistoryItem, detect_patterns
from app.services.recurring_detection import within_tolerance as amount_within_tolerance
from app.services.recurring_schedule import (
    ScheduleRule,
    calendar_icon,
    days_until,
    due_status,
    is_occurrence,
    next_occurrence,
)

SUGGESTIONS_KEY = "recurring.suggestions"
DISMISSED_KEY = "recurring.dismissed_suggestions"
DEFAULT_LOOKBACK_DAYS = 180
MAX_DETECTION_DAYS = 731
MAX_DISMISSED = 200

# ---------- lịch ----------


def rule_of(recurring: RecurringTransaction) -> ScheduleRule:
    return ScheduleRule(
        recurring.frequency,
        day_of_month=recurring.day_of_month,
        day_of_week=recurring.day_of_week,
        month=recurring.next_due_on.month if recurring.frequency == "yearly" else None,
    )


def _resolve_schedule(
    frequency: str,
    day_of_month: int | None,
    day_of_week: int | None,
    next_due_on: date | None,
    today: date,
) -> tuple[int | None, int | None, date]:
    """Chuẩn hoá lịch → `(day_of_month, day_of_week, next_due_on)`; thiếu thì suy ra, mâu thuẫn →
    422. Không gửi `next_due_on` → kỳ đầu tiên sau hôm nay."""
    if frequency == "weekly":
        if day_of_month is not None:
            raise DomainError("Khoản hằng tuần không có ngày trong tháng", "invalid_schedule")
        if day_of_week is None:
            if next_due_on is None:
                raise DomainError("Chọn thứ trong tuần cho khoản hằng tuần", "invalid_schedule")
            day_of_week = next_due_on.isoweekday()
        rule = ScheduleRule("weekly", day_of_week=day_of_week)
    else:
        if day_of_week is not None:
            raise DomainError(
                "Khoản hằng tháng / hằng năm không có thứ trong tuần", "invalid_schedule"
            )
        if frequency == "yearly" and next_due_on is None:
            raise DomainError("Khoản hằng năm cần ngày đến hạn kế tiếp", "invalid_schedule")
        if day_of_month is None:
            if next_due_on is None:
                raise DomainError("Chọn ngày trong tháng cho khoản hằng tháng", "invalid_schedule")
            day_of_month = next_due_on.day
        rule = ScheduleRule(
            frequency,
            day_of_month=day_of_month,
            month=next_due_on.month if next_due_on is not None else None,
        )
    if next_due_on is None:
        next_due_on = next_occurrence(rule, today)
    elif not is_occurrence(rule, next_due_on):
        raise DomainError(
            "Ngày đến hạn kế tiếp không khớp lịch (ngày trong tháng / thứ trong tuần)",
            "next_due_on_mismatch",
        )
    return rule.day_of_month, rule.day_of_week, next_due_on


# ---------- đọc ----------


def to_read(recurring: RecurringTransaction, today: date, transaction_count: int) -> RecurringRead:
    return RecurringRead(
        id=recurring.id,
        name=recurring.name,
        direction=recurring.direction,  # type: ignore[arg-type]
        amount=recurring.amount,
        category_id=recurring.category_id,
        category=CategoryBrief.model_validate(recurring.category),
        spending_type=recurring.spending_type,  # type: ignore[arg-type]
        frequency=recurring.frequency,  # type: ignore[arg-type]
        day_of_month=recurring.day_of_month,
        day_of_week=recurring.day_of_week,
        next_due_on=recurring.next_due_on,
        auto_detected=recurring.auto_detected,
        active=recurring.active,
        icon=icon_of(recurring),
        days_until_due=days_until(recurring.next_due_on, today),
        due_status=due_status(recurring.next_due_on, today),  # type: ignore[arg-type]
        transaction_count=transaction_count,
        created_at=recurring.created_at,
        updated_at=recurring.updated_at,
    )


def icon_of(recurring: RecurringTransaction) -> str:
    return calendar_icon(recurring.direction, recurring.category.slug, recurring.name)


def _read(db: Session, recurring: RecurringTransaction, today: date) -> RecurringRead:
    counts = recurring_repository.transaction_counts(db, [recurring.id])
    return to_read(recurring, today, counts.get(recurring.id, 0))


def get_recurring(db: Session, recurring_id: uuid.UUID) -> RecurringTransaction:
    recurring = recurring_repository.get(db, recurring_id)
    if recurring is None:
        raise NotFoundError("Không tìm thấy khoản định kỳ", "recurring_not_found")
    return recurring


def list_recurring(db: Session, today: date, active: bool | None = None) -> RecurringList:
    items = recurring_repository.list_recurring(db, active=active)
    counts = recurring_repository.transaction_counts(db, [r.id for r in items])
    return RecurringList(items=[to_read(r, today, counts.get(r.id, 0)) for r in items])


def list_active(db: Session) -> list[RecurringTransaction]:
    return recurring_repository.list_recurring(db, active=True)


# ---------- ghi ----------


def _resolve_category(
    db: Session, category_id: uuid.UUID, direction: str, spending_type: str | None, *, keep: bool
) -> tuple[Category, str | None]:
    category = transaction_service.resolve_category(db, category_id, direction, allow_archived=keep)
    return category, transaction_service.resolve_spending_type(direction, spending_type, category)


def create_recurring(
    db: Session, data: RecurringCreate, today: date, *, auto_detected: bool = False
) -> RecurringRead:
    recurring = _build(db, data, today, auto_detected=auto_detected)
    db.commit()
    db.refresh(recurring)
    return _read(db, recurring, today)


def _build(
    db: Session, data: RecurringCreate, today: date, *, auto_detected: bool
) -> RecurringTransaction:
    category, spending_type = _resolve_category(
        db, data.category_id, data.direction, data.spending_type, keep=False
    )
    day_of_month, day_of_week, next_due_on = _resolve_schedule(
        data.frequency, data.day_of_month, data.day_of_week, data.next_due_on, today
    )
    recurring = RecurringTransaction(
        name=data.name,
        direction=data.direction,
        amount=data.amount,
        category=category,
        spending_type=spending_type,
        frequency=data.frequency,
        day_of_month=day_of_month,
        day_of_week=day_of_week,
        next_due_on=next_due_on,
        auto_detected=auto_detected,
        active=True,
    )
    return recurring_repository.add(db, recurring)


def update_recurring(
    db: Session, recurring_id: uuid.UUID, data: RecurringUpdate, today: date
) -> RecurringRead:
    recurring = get_recurring(db, recurring_id)
    changes = data.model_dump(exclude_unset=True)

    direction = changes.get("direction", recurring.direction)
    category_id = changes.get("category_id", recurring.category_id)
    category_changed = category_id != recurring.category_id
    if "spending_type" in changes:
        spending_type = changes["spending_type"]
    elif direction == "expense" and recurring.direction == "expense" and not category_changed:
        spending_type = recurring.spending_type
    else:
        spending_type = None
    category, spending_type = _resolve_category(
        db, category_id, direction, spending_type, keep=not category_changed
    )

    frequency = changes.get("frequency", recurring.frequency)
    if frequency != recurring.frequency:
        # Đổi tần suất: ngày cũ của tần suất khác không còn nghĩa.
        day_of_month = changes.get("day_of_month")
        day_of_week = changes.get("day_of_week")
    else:
        day_of_month = changes.get("day_of_month", recurring.day_of_month)
        day_of_week = changes.get("day_of_week", recurring.day_of_week)
    schedule_changed = (frequency, day_of_month, day_of_week) != (
        recurring.frequency,
        recurring.day_of_month,
        recurring.day_of_week,
    )
    if "next_due_on" in changes:
        next_due_on: date | None = changes["next_due_on"]
    elif not schedule_changed:
        next_due_on = recurring.next_due_on
    elif frequency == "yearly":
        # Giữ tháng của kỳ hiện tại, đổi ngày → kỳ đầu tiên sau hôm nay.
        day_of_month = day_of_month or recurring.next_due_on.day
        rule = ScheduleRule("yearly", day_of_month=day_of_month, month=recurring.next_due_on.month)
        next_due_on = next_occurrence(rule, today)
    else:
        next_due_on = None
    day_of_month, day_of_week, next_due_on = _resolve_schedule(
        frequency, day_of_month, day_of_week, next_due_on, today
    )
    reactivated = changes.get("active") is True and not recurring.active
    if reactivated and "next_due_on" not in changes and next_due_on < today:
        rule = ScheduleRule(
            frequency,
            day_of_month=day_of_month,
            day_of_week=day_of_week,
            month=next_due_on.month if frequency == "yearly" else None,
        )
        next_due_on = next_occurrence(rule, today)

    recurring.direction = direction
    recurring.category = category
    recurring.spending_type = spending_type
    recurring.frequency = frequency
    recurring.day_of_month = day_of_month
    recurring.day_of_week = day_of_week
    recurring.next_due_on = next_due_on
    for field in ("name", "amount", "active"):
        if field in changes:
            setattr(recurring, field, changes[field])
    db.commit()
    db.refresh(recurring)
    return _read(db, recurring, today)


def deactivate_recurring(db: Session, recurring_id: uuid.UUID) -> None:
    """DELETE = tắt (giữ lịch sử giao dịch đã gắn)."""
    recurring = get_recurring(db, recurring_id)
    recurring.active = False
    db.commit()


def create_transaction_from_recurring(
    db: Session, recurring_id: uuid.UUID, data: RecurringTransactionCreate, today: date
) -> tuple[Transaction, RecurringRead]:
    recurring = get_recurring(db, recurring_id)
    if not recurring.active:
        raise ConflictError(
            "Khoản định kỳ đang tắt — bật lại trước khi tạo giao dịch", "recurring_inactive"
        )
    category, spending_type = _resolve_category(
        db, recurring.category_id, recurring.direction, recurring.spending_type, keep=False
    )
    due = recurring.next_due_on
    transaction = Transaction(
        direction=recurring.direction,
        amount=data.amount or recurring.amount,
        occurred_on=data.occurred_on or min(due, today),
        note=recurring.name,
        category=category,
        spending_type=spending_type,
        source="recurring",
        recurring_id=recurring.id,
    )
    transaction_repository.add(db, transaction)
    recurring.next_due_on = next_occurrence(rule_of(recurring), due)
    db.commit()
    db.refresh(transaction)
    db.refresh(recurring)
    return transaction, _read(db, recurring, today)


# ---------- phát hiện ----------


def _load_suggestions(db: Session) -> tuple[RecurringSuggestionList, bool]:
    raw = app_setting_repository.get_value(db, SUGGESTIONS_KEY)
    if not isinstance(raw, dict):
        return RecurringSuggestionList(from_date=None, to_date=None, suggestions=[]), False
    try:
        return RecurringSuggestionList.model_validate(raw), True
    except ValidationError:
        return RecurringSuggestionList(from_date=None, to_date=None, suggestions=[]), False


def _save_suggestions(db: Session, data: RecurringSuggestionList) -> None:
    app_setting_repository.set_value(db, SUGGESTIONS_KEY, data.model_dump(mode="json"))


def _dismissed_keys(db: Session) -> list[str]:
    raw = app_setting_repository.get_value(db, DISMISSED_KEY)
    return [k for k in raw if isinstance(k, str)] if isinstance(raw, list) else []


def _covered_by_existing(
    pattern: DetectedPattern | RecurringSuggestion, recurrings: list[RecurringTransaction]
) -> bool:
    """Mẫu đã có khoản định kỳ đang bật cùng chiều + danh mục + tần suất, số tiền ±10%."""
    return any(
        r.direction == pattern.direction
        and r.category_id == pattern.category_id
        and r.frequency == pattern.frequency
        and amount_within_tolerance(pattern.amount, r.amount)
        for r in recurrings
    )


def _to_suggestion(pattern: DetectedPattern, category: Category) -> RecurringSuggestion:
    return RecurringSuggestion(
        id=pattern.suggestion_id,
        name=pattern.name or category.name,
        direction=pattern.direction,  # type: ignore[arg-type]
        amount=pattern.amount,
        category_id=pattern.category_id,
        category_name=category.name,
        spending_type=pattern.spending_type,  # type: ignore[arg-type]
        frequency=pattern.frequency,  # type: ignore[arg-type]
        day_of_month=pattern.day_of_month,
        day_of_week=pattern.day_of_week,
        next_due_on=pattern.next_due_on,
        icon=calendar_icon(pattern.direction, category.slug, pattern.name or category.name),
        confidence=_ratio(pattern.confidence),
        amount_consistency=_ratio(pattern.amount_consistency),
        interval_consistency=_ratio(pattern.interval_consistency),
        median_interval_days=_ratio(pattern.median_interval_days, places=1),
        occurrences=len(pattern.items),
        first_occurred_on=pattern.items[0].occurred_on,
        last_occurred_on=pattern.items[-1].occurred_on,
        amounts=[i.amount for i in pattern.items],
        transaction_ids=[i.id for i in pattern.items],
    )


def _ratio(value: Fraction, places: int = 2) -> float:
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return float(exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def detect(db: Session, data: RecurringDetectRequest, today: date) -> RecurringSuggestionList:
    """Chạy phát hiện trên giao dịch chưa gắn khoản định kỳ trong `[from_date, to_date]`; ghi đè
    danh sách đề xuất đã lưu. **Không tạo khoản định kỳ nào.**"""
    to_date = data.to_date or today
    from_date = data.from_date or to_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    if from_date > to_date:
        raise DomainError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc", "invalid_date_range")
    if (to_date - from_date).days > MAX_DETECTION_DAYS:
        raise DomainError("Khoảng phát hiện tối đa 2 năm", "invalid_date_range")

    transactions = recurring_repository.unlinked_transactions_between(db, from_date, to_date)
    history = [
        HistoryItem(
            id=t.id,
            occurred_on=t.occurred_on,
            amount=t.amount,
            direction=t.direction,
            category_id=t.category_id,
            spending_type=t.spending_type,
            note=t.note,
        )
        for t in transactions
    ]
    categories = {t.category_id: t.category for t in transactions}
    dismissed = set(_dismissed_keys(db))
    existing = list_active(db)
    suggestions: list[RecurringSuggestion] = []
    seen: set[uuid.UUID] = set()
    for pattern in detect_patterns(history, to_date=to_date, today=today):
        if pattern.key in dismissed or pattern.suggestion_id in seen:
            continue
        if _covered_by_existing(pattern, existing):
            continue
        seen.add(pattern.suggestion_id)
        suggestions.append(_to_suggestion(pattern, categories[pattern.category_id]))
    result = RecurringSuggestionList(from_date=from_date, to_date=to_date, suggestions=suggestions)
    _save_suggestions(db, result)
    db.commit()
    return result


def list_suggestions(db: Session) -> RecurringSuggestionList:
    """Đề xuất của lần phát hiện gần nhất, bỏ mẫu đã có khoản định kỳ đang bật."""
    stored, _ = _load_suggestions(db)
    existing = list_active(db)
    stored.suggestions = [s for s in stored.suggestions if not _covered_by_existing(s, existing)]
    return stored


def _find_suggestion(
    db: Session, suggestion_id: uuid.UUID
) -> tuple[RecurringSuggestionList, RecurringSuggestion]:
    stored, _ = _load_suggestions(db)
    for suggestion in stored.suggestions:
        if suggestion.id == suggestion_id:
            return stored, suggestion
    raise NotFoundError(
        "Không tìm thấy đề xuất (có thể đã xử lý) — chạy phát hiện lại", "suggestion_not_found"
    )


def _remove_suggestion(
    db: Session, stored: RecurringSuggestionList, suggestion_id: uuid.UUID
) -> None:
    stored.suggestions = [s for s in stored.suggestions if s.id != suggestion_id]
    _save_suggestions(db, stored)


def _suggestion_key(s: RecurringSuggestion) -> str:
    anchor = s.day_of_month if s.frequency == "monthly" else s.day_of_week
    return "|".join(
        [s.direction, str(s.category_id), s.spending_type or "-", s.frequency, str(anchor)]
    )


def confirm_suggestion(
    db: Session, suggestion_id: uuid.UUID, data: RecurringSuggestionConfirm, today: date
) -> RecurringRead:
    """User xác nhận → tạo khoản định kỳ `auto_detected` + gắn giao dịch lịch sử của mẫu
    (1 commit; lỗi → không ghi gì)."""
    stored, suggestion = _find_suggestion(db, suggestion_id)
    default_due = suggestion.next_due_on if suggestion.next_due_on > today else None
    recurring = _build(
        db,
        RecurringCreate(
            name=data.name or suggestion.name,
            direction=suggestion.direction,
            amount=data.amount or suggestion.amount,
            category_id=suggestion.category_id,
            spending_type=suggestion.spending_type,
            frequency=suggestion.frequency,
            day_of_month=suggestion.day_of_month,
            day_of_week=suggestion.day_of_week,
            next_due_on=data.next_due_on or default_due,
        ),
        today,
        auto_detected=True,
    )
    recurring_repository.link_transactions(db, suggestion.transaction_ids, recurring.id)
    _remove_suggestion(db, stored, suggestion_id)
    db.commit()
    db.refresh(recurring)
    return _read(db, recurring, today)


def dismiss_suggestion(db: Session, suggestion_id: uuid.UUID) -> None:
    stored, suggestion = _find_suggestion(db, suggestion_id)
    _remove_suggestion(db, stored, suggestion_id)
    keys = [k for k in _dismissed_keys(db) if k != _suggestion_key(suggestion)]
    keys.append(_suggestion_key(suggestion))
    app_setting_repository.set_value(db, DISMISSED_KEY, keys[-MAX_DISMISSED:])
    db.commit()
