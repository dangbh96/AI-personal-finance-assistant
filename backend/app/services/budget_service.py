"""Budget engine (Phase 4) — deterministic, không gọi AI (ADR-005). Tiền là số nguyên đồng.

Ba chiến lược tạo phân bổ mặc định (user chỉnh lại trước khi lưu):
- `envelope`: 5 hũ preset (Essential/Fun/Shopping/Saving/Unexpected), hũ → danh mục lưu ở
  `app_settings.budget_jar_category_map`.
- `fifty_thirty_twenty`: 50% essential / 30% wants / 20% savings — chỉ là **tham khảo**.
- `pyf`: trích `savings_target` trước, phần còn lại chia essential/wants/irregular 60/30/10.

Cách mỗi dòng phân bổ khớp giao dịch (Phase 5 dùng `allocation_scope`):
- dòng có `category_id` → giao dịch chi của danh mục đó;
- dòng `jar_name` của budget `envelope` → giao dịch chi thuộc các danh mục của hũ;
- dòng `jar_name` của budget `fifty_thirty_twenty` / `pyf` (dòng nhóm, `jar_name = group`) →
  giao dịch chi có `spending_type` tương ứng nhóm (`GROUP_SPENDING_TYPES`); `savings` không khớp
  giao dịch chi nào.

Vùng linh hoạt (Phase 9) do `zone_service` tính; ở đây chỉ giữ / xoá cột vùng khi ghi lại dòng
phân bổ (`_zone_fields`, `set_allocation_planned`).
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models import Budget, BudgetAllocation, Category
from app.repositories import app_setting_repository, budget_repository, category_repository
from app.schemas.budget import (
    BudgetAllocationDraft,
    BudgetAllocationInput,
    BudgetAllocationRead,
    BudgetCreate,
    BudgetDraft,
    BudgetJarList,
    BudgetJarRead,
    BudgetPreviewRequest,
    BudgetPreviewResponse,
    BudgetRead,
    BudgetTotals,
    BudgetUpdate,
    BudgetWarning,
    FiftyThirtyTwentyReference,
    GroupTotals,
    ReferenceComparison,
)
from app.schemas.category import CategoryBrief
from app.services.money import add_months, allocate_by_weights, format_vnd

JAR_MAP_KEY = "budget_jar_category_map"
AMOUNT_STEP = 1_000


@dataclass(frozen=True)
class JarPreset:
    name: str
    group: str
    percent: int


ENVELOPE_PRESET: tuple[JarPreset, ...] = (
    JarPreset("Essential", "essential", 52),
    JarPreset("Fun", "wants", 12),
    JarPreset("Shopping", "wants", 8),
    JarPreset("Saving", "savings", 20),
    JarPreset("Unexpected", "irregular", 8),
)
FIFTY_THIRTY_TWENTY: tuple[tuple[str, int], ...] = (
    ("essential", 50),
    ("wants", 30),
    ("savings", 20),
)
PYF_REMAINING_SPLIT: tuple[tuple[str, int], ...] = (
    ("essential", 60),
    ("wants", 30),
    ("irregular", 10),
)
GROUP_SPENDING_TYPES: dict[str, frozenset[str]] = {
    "essential": frozenset({"essential"}),
    "wants": frozenset({"non_essential"}),
    "irregular": frozenset({"irregular"}),
    "savings": frozenset(),
}
GROUP_LABELS = {
    "essential": "Thiết yếu",
    "wants": "Mong muốn",
    "savings": "Tiết kiệm",
    "irregular": "Bất thường",
}
# Tên hũ preset (lưu tiếng Anh trong `jar_name`) → tên hiển thị (khớp frontend `JAR_LABELS`).
JAR_LABELS = {
    "Essential": "Thiết yếu",
    "Fun": "Vui chơi",
    "Shopping": "Mua sắm",
    "Saving": "Tiết kiệm",
    "Unexpected": "Dự phòng",
}
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"draft", "closed"},
    "closed": {"active"},
}


class _AllocationLike(Protocol):
    group: str
    category_id: uuid.UUID | None
    jar_name: str | None
    planned_amount: int


# ---------- chiến lược (thuần, không đụng DB) ----------


def _group_rows(split: Sequence[tuple[str, int]], total: int) -> list[BudgetAllocationInput]:
    amounts = allocate_by_weights(total, [percent for _, percent in split], AMOUNT_STEP)
    return [
        BudgetAllocationInput(group=group, jar_name=group, planned_amount=amount)
        for (group, _), amount in zip(split, amounts, strict=True)
    ]


def create_envelope_budget(expected_income: int) -> list[BudgetAllocationInput]:
    """5 hũ preset theo % thu nhập (52/12/8/20/8)."""
    amounts = allocate_by_weights(
        expected_income, [jar.percent for jar in ENVELOPE_PRESET], AMOUNT_STEP
    )
    return [
        BudgetAllocationInput(group=jar.group, jar_name=jar.name, planned_amount=amount)
        for jar, amount in zip(ENVELOPE_PRESET, amounts, strict=True)
    ]


def fifty_thirty_twenty_amounts(expected_income: int) -> dict[str, int]:
    return {
        row.group: row.planned_amount for row in _group_rows(FIFTY_THIRTY_TWENTY, expected_income)
    }


def create_fifty_thirty_twenty_reference(expected_income: int) -> list[BudgetAllocationInput]:
    """Phân bổ 50/30/20 theo nhóm — dùng làm budget nếu user chọn, nhưng chỉ là tham khảo."""
    return _group_rows(FIFTY_THIRTY_TWENTY, expected_income)


def create_pyf_budget(expected_income: int, savings_target: int) -> list[BudgetAllocationInput]:
    """Pay Yourself First: dòng savings = `savings_target` trước, phần còn lại chia 60/30/10."""
    if savings_target > expected_income:
        raise DomainError(
            f"Mục tiêu tiết kiệm ({format_vnd(savings_target)}) lớn hơn thu nhập dự kiến "
            f"({format_vnd(expected_income)})",
            "savings_target_exceeds_income",
        )
    savings = BudgetAllocationInput(
        group="savings", jar_name="savings", planned_amount=savings_target
    )
    return [savings, *_group_rows(PYF_REMAINING_SPLIT, expected_income - savings_target)]


def generate_allocations(
    strategy: str, expected_income: int, savings_target: int | None
) -> list[BudgetAllocationInput]:
    if strategy == "envelope":
        return create_envelope_budget(expected_income)
    if strategy == "fifty_thirty_twenty":
        return create_fifty_thirty_twenty_reference(expected_income)
    if savings_target is None:
        raise DomainError("Pay Yourself First cần mục tiêu tiết kiệm", "savings_target_required")
    return create_pyf_budget(expected_income, savings_target)


# ---------- tổng, so sánh, cảnh báo (thuần) ----------


def compute_totals(expected_income: int, allocations: Iterable[_AllocationLike]) -> BudgetTotals:
    by_group = dict.fromkeys(GROUP_SPENDING_TYPES, 0)
    for allocation in allocations:
        by_group[allocation.group] += allocation.planned_amount
    planned_total = sum(by_group.values())
    return BudgetTotals(
        planned_total=planned_total,
        unallocated=expected_income - planned_total,
        by_group=GroupTotals(**by_group),
    )


def savings_total(allocations: Iterable[_AllocationLike]) -> int:
    return sum(a.planned_amount for a in allocations if a.group == "savings")


def compare_with_reference(
    expected_income: int, allocations: Iterable[_AllocationLike]
) -> FiftyThirtyTwentyReference:
    """So budget với tham khảo 50/30/20. Nhóm `irregular` tính vào `wants` khi so sánh."""
    reference = fifty_thirty_twenty_amounts(expected_income)
    by_group = compute_totals(expected_income, allocations).by_group
    planned = {
        "essential": by_group.essential,
        "wants": by_group.wants + by_group.irregular,
        "savings": by_group.savings,
    }
    return FiftyThirtyTwentyReference(
        **reference,
        comparison=[
            ReferenceComparison(
                group=group,
                planned=planned[group],
                reference=reference[group],
                difference=planned[group] - reference[group],
            )
            for group, _ in FIFTY_THIRTY_TWENTY
        ],
    )


def over_income_amount(expected_income: int, allocations: Iterable[_AllocationLike]) -> int:
    """Phần tổng planned vượt thu nhập dự kiến (0 nếu không vượt)."""
    return max(0, sum(a.planned_amount for a in allocations) - expected_income)


def _over_income_warning(amount: int) -> BudgetWarning:
    return BudgetWarning(
        code="planned_exceeds_income",
        message=f"Tổng phân bổ vượt thu nhập dự kiến {format_vnd(amount)}.",
        amount=amount,
    )


# ---------- phạm vi khớp giao dịch (dùng ở Phase 5) ----------


@dataclass(frozen=True)
class AllocationScope:
    kind: Literal["category", "jar", "group"]
    category_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    spending_types: frozenset[str] = field(default_factory=frozenset)


def allocation_scope(
    strategy: str,
    allocation: _AllocationLike,
    jar_categories: Mapping[str, Iterable[uuid.UUID]],
) -> AllocationScope:
    """Giao dịch chi nào thuộc dòng phân bổ này (xem docstring module)."""
    if allocation.category_id is not None:
        return AllocationScope("category", category_ids=frozenset({allocation.category_id}))
    if strategy == "envelope":
        jar = allocation.jar_name or ""
        return AllocationScope("jar", category_ids=frozenset(jar_categories.get(jar, ())))
    return AllocationScope("group", spending_types=GROUP_SPENDING_TYPES[allocation.group])


def load_jar_map(db: Session) -> dict[str, list[str]]:
    """`app_settings.budget_jar_category_map`: tên hũ → slug danh mục chi."""
    raw = app_setting_repository.get_value(db, JAR_MAP_KEY)
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): [slug for slug in slugs if isinstance(slug, str)]
        for name, slugs in raw.items()
        if isinstance(slugs, list)
    }


def load_jar_categories(db: Session) -> dict[str, list[Category]]:
    """Hũ → danh mục chi (kể cả đã ẩn — giao dịch cũ vẫn thuộc hũ). Slug không tồn tại bị bỏ."""
    by_slug = {
        c.slug: c
        for c in category_repository.list_categories(db, kind="expense", include_archived=True)
    }
    return {
        name: [by_slug[slug] for slug in slugs if slug in by_slug]
        for name, slugs in load_jar_map(db).items()
    }


def _jar_order(name: str) -> tuple[int, str]:
    names = [jar.name for jar in ENVELOPE_PRESET]
    return (names.index(name) if name in names else len(names), name)


def list_jars(db: Session) -> BudgetJarList:
    presets = {jar.name: jar for jar in ENVELOPE_PRESET}
    jars = load_jar_categories(db)
    return BudgetJarList(
        items=[
            BudgetJarRead(
                name=name,
                group=presets[name].group if name in presets else None,
                default_percent=presets[name].percent if name in presets else None,
                categories=[CategoryBrief.model_validate(c) for c in jars[name]],
            )
            for name in sorted(jars, key=_jar_order)
        ]
    )


# ---------- validate ----------


def allocation_label(category_name: str | None, jar_name: str | None) -> str:
    """Tên hiển thị của dòng phân bổ: danh mục, hũ preset, nhóm, hoặc `jar_name` gốc."""
    if category_name:
        return category_name
    jar = jar_name or ""
    return JAR_LABELS.get(jar) or GROUP_LABELS.get(jar, jar)


def _row_label(allocation: _AllocationLike, categories: Mapping[uuid.UUID, Category]) -> str:
    if allocation.category_id is not None:
        return categories[allocation.category_id].name
    return GROUP_LABELS.get(allocation.jar_name or "", allocation.jar_name or "")


def _validate_allocations(
    db: Session, strategy: str, allocations: Sequence[BudgetAllocationInput]
) -> dict[uuid.UUID, Category]:
    """Kiểm tra từng dòng và không có 2 dòng cùng khớp một giao dịch (tránh đếm trùng actual).

    Trả danh mục của các dòng theo danh mục.
    """
    categories: dict[uuid.UUID, Category] = {}
    jar_categories = load_jar_categories(db) if strategy == "envelope" else {}
    seen_rows: set[tuple[str, object]] = set()
    for allocation in allocations:
        if allocation.category_id is not None:
            category = category_repository.get(db, allocation.category_id)
            if category is None:
                raise DomainError("Danh mục không tồn tại", "category_not_found")
            if category.kind != "expense":
                raise DomainError(
                    f"Danh mục '{category.name}' là thu nhập, không phân bổ ngân sách được",
                    "category_kind_mismatch",
                )
            if category.is_archived:
                raise DomainError(f"Danh mục '{category.name}' đã bị ẩn", "category_archived")
            categories[category.id] = category
            key: tuple[str, object] = ("category", category.id)
        elif strategy == "envelope":
            if allocation.jar_name not in jar_categories:
                raise DomainError(
                    f"Không có hũ '{allocation.jar_name}' trong cấu hình hũ", "unknown_jar"
                )
            key = ("jar", allocation.jar_name)
        else:
            if allocation.jar_name != allocation.group:
                raise DomainError(
                    "Với 50/30/20 và Pay Yourself First, dòng theo nhóm phải có jar_name = group "
                    f"(nhận '{allocation.jar_name}' cho nhóm '{allocation.group}')",
                    "invalid_group_row",
                )
            key = ("group", allocation.group)
        if key in seen_rows:
            raise DomainError(
                f"Dòng '{_row_label(allocation, categories)}' bị lặp", "duplicate_allocation"
            )
        seen_rows.add(key)

    jar_ids = {name: [c.id for c in cats] for name, cats in jar_categories.items()}
    names = {c.id: c.name for cats in jar_categories.values() for c in cats}
    names.update({category_id: c.name for category_id, c in categories.items()})
    owner: dict[uuid.UUID, str] = {}
    group_row: str | None = None
    category_row: str | None = None
    for allocation in allocations:
        scope = allocation_scope(strategy, allocation, jar_ids)
        label = _row_label(allocation, categories)
        if scope.spending_types:
            group_row = group_row or label
        if scope.category_ids:
            category_row = category_row or label
        for category_id in scope.category_ids:
            if category_id in owner:
                raise DomainError(
                    f"Danh mục '{names[category_id]}' nằm trong cả '{owner[category_id]}' và "
                    f"'{label}' — "
                    "chi tiêu sẽ bị tính hai lần",
                    "overlapping_allocations",
                )
            owner[category_id] = label
    if group_row and category_row:
        raise DomainError(
            f"Không thể vừa phân bổ theo nhóm ('{group_row}') vừa theo danh mục "
            f"('{category_row}') — chi tiêu sẽ bị tính hai lần",
            "overlapping_allocations",
        )
    return categories


def _check_over_income(
    expected_income: int, allocations: Sequence[_AllocationLike], confirmed: bool
) -> None:
    amount = over_income_amount(expected_income, allocations)
    if amount and not confirmed:
        raise DomainError(
            f"Tổng phân bổ vượt thu nhập dự kiến {format_vnd(amount)}. "
            "Gửi confirm_over_income=true nếu bạn vẫn muốn lưu.",
            "planned_exceeds_income",
        )


# ---------- preview ----------


def _to_draft(
    allocation: BudgetAllocationInput, categories: Mapping[uuid.UUID, Category]
) -> BudgetAllocationDraft:
    category = categories.get(allocation.category_id) if allocation.category_id else None
    return BudgetAllocationDraft(
        **allocation.model_dump(),
        category=CategoryBrief.model_validate(category) if category else None,
    )


def _unmapped_categories_warning(
    db: Session, allocations: Sequence[BudgetAllocationInput]
) -> BudgetWarning | None:
    covered = {a.category_id for a in allocations if a.category_id}
    jar_names = {a.jar_name for a in allocations if a.jar_name}
    for name, cats in load_jar_categories(db).items():
        if name in jar_names:
            covered.update(c.id for c in cats)
    missing = [
        c.name
        for c in category_repository.list_categories(db, kind="expense")
        if c.id not in covered
    ]
    if not missing:
        return None
    return BudgetWarning(
        code="categories_not_in_jar",
        message="Các danh mục chưa thuộc hũ nào nên chi tiêu của chúng sẽ không được tính: "
        + ", ".join(missing)
        + ".",
    )


def preview_budget(db: Session, data: BudgetPreviewRequest) -> BudgetPreviewResponse:
    """Tính phân bổ mặc định (hoặc kiểm tra phân bổ đã chỉnh) — **không ghi DB**."""
    allocations = (
        data.allocations
        if data.allocations is not None
        else generate_allocations(data.strategy, data.expected_income, data.savings_target)
    )
    categories = _validate_allocations(db, data.strategy, allocations)

    warnings: list[BudgetWarning] = []
    if over := over_income_amount(data.expected_income, allocations):
        warnings.append(_over_income_warning(over))
    if data.strategy == "envelope" and (unmapped := _unmapped_categories_warning(db, allocations)):
        warnings.append(unmapped)
    if (existing := budget_repository.get_by_month(db, data.period_month)) is not None:
        warnings.append(
            BudgetWarning(
                code="budget_exists",
                message=f"Tháng {data.period_month:%m/%Y} đã có ngân sách "
                f"({'đang dùng' if existing.status == 'active' else existing.status}).",
            )
        )

    return BudgetPreviewResponse(
        budget=BudgetDraft(
            period_month=data.period_month,
            strategy=data.strategy,
            expected_income=data.expected_income,
            savings_target=savings_total(allocations),
            allocations=[_to_draft(a, categories) for a in allocations],
            totals=compute_totals(data.expected_income, allocations),
        ),
        reference_50_30_20=compare_with_reference(data.expected_income, allocations),
        warnings=warnings,
    )


# ---------- CRUD ----------


def to_read(budget: Budget) -> BudgetRead:
    allocations = list(budget.allocations)
    return BudgetRead(
        id=budget.id,
        period_month=budget.period_month,
        strategy=budget.strategy,  # type: ignore[arg-type]
        expected_income=budget.expected_income,
        savings_target=budget.savings_target,
        status=budget.status,  # type: ignore[arg-type]
        allocations=[BudgetAllocationRead.model_validate(a) for a in allocations],
        totals=compute_totals(budget.expected_income, allocations),
        reference_50_30_20=compare_with_reference(budget.expected_income, allocations),
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def get_budget(db: Session, budget_id: uuid.UUID) -> Budget:
    budget = budget_repository.get(db, budget_id)
    if budget is None:
        raise NotFoundError("Không tìm thấy ngân sách", "budget_not_found")
    return budget


def list_budgets(
    db: Session, *, date_from: date | None = None, date_to: date | None = None
) -> list[Budget]:
    if date_from and date_to and date_from > date_to:
        raise DomainError("Tháng bắt đầu phải trước hoặc bằng tháng kết thúc", "invalid_date_range")
    return budget_repository.list_budgets(db, date_from=date_from, date_to=date_to)


def _ensure_month_free(db: Session, period_month: date) -> None:
    if budget_repository.get_by_month(db, period_month) is not None:
        raise ConflictError(
            f"Tháng {period_month:%m/%Y} đã có ngân sách — mở ngân sách đó để chỉnh sửa",
            "budget_exists",
        )


def _zone_fields(
    source: BudgetAllocation | None, planned_amount: int, *, keep_auto_cache: bool
) -> dict[str, object]:
    """Cột vùng linh hoạt (Phase 9) mang sang dòng mới từ dòng cũ cùng danh mục / hũ.

    Ngưỡng `manual` (user nhập) luôn giữ. Ngưỡng `auto` là cache tính theo planned và lịch sử
    trước tháng ngân sách — chỉ giữ khi cùng tháng và planned không đổi, ngược lại để NULL (chưa
    tính, user bấm tính lại).
    """
    if source is None:
        return {}
    keep = source.zone_mode == "manual" or (
        keep_auto_cache and source.planned_amount == planned_amount
    )
    return {
        "zone_mode": source.zone_mode,
        "comfort_low": source.comfort_low if keep else None,
        "comfort_high": source.comfort_high if keep else None,
        "warning_threshold": source.warning_threshold if keep else None,
    }


def _set_allocations(
    budget: Budget,
    allocations: Sequence[BudgetAllocationInput | BudgetAllocation],
    *,
    keep_auto_cache: bool = True,
) -> None:
    """Thay toàn bộ dòng phân bổ. Vùng linh hoạt lấy từ dòng cũ cùng danh mục / hũ (sửa budget)
    hoặc từ chính dòng nguồn (copy tháng)."""
    previous = list(budget.allocations)

    def source_of(a: BudgetAllocationInput | BudgetAllocation) -> BudgetAllocation | None:
        if isinstance(a, BudgetAllocation):
            return a
        return next((p for p in previous if _same_line(p, a)), None)

    budget.allocations = [
        BudgetAllocation(
            group=a.group,
            category_id=a.category_id,
            jar_name=a.jar_name,
            planned_amount=a.planned_amount,
            position=position,
            **_zone_fields(source_of(a), a.planned_amount, keep_auto_cache=keep_auto_cache),
        )
        for position, a in enumerate(allocations)
    ]
    budget.savings_target = savings_total(allocations)


def create_budget(db: Session, data: BudgetCreate) -> Budget:
    if data.status == "closed":
        raise DomainError("Ngân sách mới chỉ có thể là draft hoặc active", "invalid_status")
    _ensure_month_free(db, data.period_month)
    _validate_allocations(db, data.strategy, data.allocations)
    _check_over_income(data.expected_income, data.allocations, data.confirm_over_income)

    budget = Budget(
        period_month=data.period_month,
        strategy=data.strategy,
        expected_income=data.expected_income,
        status=data.status,
    )
    _set_allocations(budget, data.allocations)
    budget_repository.add(db, budget)
    db.commit()
    db.refresh(budget)
    return budget


def update_budget(db: Session, budget_id: uuid.UUID, data: BudgetUpdate) -> Budget:
    budget = get_budget(db, budget_id)
    fields = data.model_fields_set
    edits_content = bool(fields & {"expected_income", "allocations"})
    if edits_content and budget.status == "closed":
        raise ConflictError(
            "Ngân sách đã đóng — mở lại (active) trước khi chỉnh sửa", "budget_closed"
        )
    if "status" in fields and data.status != budget.status:
        if data.status not in STATUS_TRANSITIONS[budget.status]:
            raise DomainError(
                f"Không chuyển được trạng thái từ {budget.status} sang {data.status}",
                "invalid_status_transition",
            )
        budget.status = data.status

    if edits_content:
        expected_income = (
            data.expected_income if "expected_income" in fields else budget.expected_income
        )
        allocations: Sequence[_AllocationLike]
        if "allocations" in fields:
            _validate_allocations(db, budget.strategy, data.allocations)
            allocations = data.allocations
        else:
            allocations = list(budget.allocations)
        _check_over_income(expected_income, allocations, data.confirm_over_income)
        budget.expected_income = expected_income
        if "allocations" in fields:
            _set_allocations(budget, data.allocations)
            # Thay phân bổ không đổi cột nào của `budgets` → tự cập nhật `updated_at`.
            budget.updated_at = func.now()

    db.flush()
    db.commit()
    db.refresh(budget)
    return budget


def delete_budget(db: Session, budget_id: uuid.UUID) -> None:
    budget = get_budget(db, budget_id)
    if budget.status != "draft":
        raise ConflictError(
            "Chỉ xoá được ngân sách nháp (draft) — chuyển về draft trước khi xoá",
            "budget_not_draft",
        )
    budget_repository.delete(db, budget)
    db.commit()


def copy_from_previous_month(db: Session, to_month: date, from_month: date | None = None) -> Budget:
    """Copy strategy, thu nhập dự kiến và phân bổ sang tháng mới, luôn ở trạng thái draft.

    Dòng theo danh mục đã bị ẩn không được copy.
    """
    budget = _copy_budget(db, to_month, from_month)
    db.commit()
    db.refresh(budget)
    return budget


def _copy_budget(db: Session, to_month: date, from_month: date | None = None) -> Budget:
    """Như `copy_from_previous_month` nhưng chỉ flush (caller commit)."""
    from_month = from_month or add_months(to_month, -1)
    if from_month == to_month:
        raise DomainError("Tháng nguồn và tháng đích phải khác nhau", "same_month")
    source = budget_repository.get_by_month(db, from_month)
    if source is None:
        raise NotFoundError(
            f"Tháng {from_month:%m/%Y} chưa có ngân sách để copy", "budget_not_found"
        )
    _ensure_month_free(db, to_month)

    budget = Budget(
        period_month=to_month,
        strategy=source.strategy,
        expected_income=source.expected_income,
        status="draft",
    )
    _set_allocations(
        budget,
        [a for a in source.allocations if a.category is None or not a.category.is_archived],
        keep_auto_cache=False,
    )
    budget_repository.add(db, budget)
    return budget


# ---------- áp dụng tư vấn điều chỉnh (Phase 8) ----------


def ensure_next_month_budget(
    db: Session, target_month: date, source_month: date | None = None
) -> tuple[Budget, bool]:
    """Budget của `target_month`; chưa có → tạo nháp copy từ `source_month` (mặc định tháng
    trước). Trả `(budget, vừa_tạo)`. Chỉ flush — caller commit cùng thay đổi khác."""
    existing = budget_repository.get_by_month(db, target_month)
    if existing is not None:
        return existing, False
    return _copy_budget(db, target_month, source_month), True


def _same_line(a: _AllocationLike, b: _AllocationLike) -> bool:
    if a.category_id is not None or b.category_id is not None:
        return a.category_id == b.category_id
    return a.jar_name == b.jar_name


def set_allocation_planned(
    db: Session,
    budget: Budget,
    line: _AllocationLike,
    planned_amount: int,
    *,
    confirm_over_income: bool = False,
) -> BudgetAllocation:
    """Đặt `planned_amount` cho dòng cùng danh mục / hũ với `line` trong `budget` (sửa tại chỗ,
    giữ id dòng); budget chưa có dòng đó → thêm dòng mới cuối bảng. Cùng validate như sửa
    budget (chồng lấn, danh mục ẩn, vượt thu nhập cần xác nhận). Chỉ flush — caller commit."""
    if budget.status == "closed":
        raise ConflictError(
            f"Ngân sách tháng {budget.period_month:%m/%Y} đã đóng — mở lại trước khi chỉnh sửa",
            "budget_closed",
        )
    rows = list(budget.allocations)
    match = next((a for a in rows if _same_line(a, line)), None)
    inputs = [
        BudgetAllocationInput(
            group=a.group,
            category_id=a.category_id,
            jar_name=a.jar_name,
            planned_amount=planned_amount if a is match else a.planned_amount,
        )
        for a in rows
    ]
    if match is None:
        inputs.append(
            BudgetAllocationInput(
                group=line.group,
                category_id=line.category_id,
                jar_name=None if line.category_id else line.jar_name,
                planned_amount=planned_amount,
            )
        )
    _validate_allocations(db, budget.strategy, inputs)
    _check_over_income(budget.expected_income, inputs, confirm_over_income)

    if match is None:
        match = BudgetAllocation(
            group=line.group,
            category_id=line.category_id,
            jar_name=None if line.category_id else line.jar_name,
            planned_amount=planned_amount,
            position=max((a.position for a in rows), default=-1) + 1,
        )
        budget.allocations.append(match)
    else:
        if match.zone_mode == "auto" and match.planned_amount != planned_amount:
            # Ngưỡng auto tính theo planned cũ → bỏ cache, chờ tính lại (Phase 9).
            match.comfort_low = match.comfort_high = match.warning_threshold = None
        match.planned_amount = planned_amount
    budget.savings_target = savings_total(inputs)
    budget.updated_at = func.now()
    db.flush()
    return match
