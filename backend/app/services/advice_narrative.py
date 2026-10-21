"""Văn bản tư vấn ngân sách (Phase 8) — kiểm tra output AI + template dự phòng. Deterministic.

- `allowed_numbers(evidence)`: mọi số explanation được phép dùng (lấy từ evidence đã bỏ ID).
- `validate_explanation`: 3 tầng, số ⊆ evidence, không phán xét, không tự nhận đã sửa budget,
  verdict ≠ `adjust_budget` thì không gợi ý tăng ngân sách, `adjust_budget` phải nêu planned đề
  xuất, `one_off` phải nêu giao dịch ngoại lệ.
- `template_explanation`: văn bản theo verdict, luôn qua `validate_explanation`.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any

from app.models.enums import AdviceVerdict
from app.schemas.budget_advice import (
    AdviceNarrative,
    AdviceTransaction,
    BudgetAdviceEvidence,
    BudgetAdviceExplanation,
)
from app.services import review_narrative
from app.services.money import format_vnd
from app.services.review_narrative import extract_numbers, format_pct, strip_ids

TEMPLATE_MODEL = "template"
FALLBACK_MODEL = review_narrative.FALLBACK_MODEL

VERDICT_LABELS: dict[str, str] = {
    "adjust_budget": "Budget có thể thấp hơn thực tế",
    "one_off": "Khoản bất thường một lần",
    "adjust_behavior": "Nên xem lại hành vi/nhịp chi",
    "on_track": "Đang trong kế hoạch",
}

# Giọng văn không phán xét (ai-architecture.md § 2, phase-08 § 4.3).
BANNED_PHRASES: tuple[str, ...] = (
    "bạn tiêu quá nhiều",
    "lãng phí",
    "bạn phải",
    "bạn nên ngay lập tức",
    "sai lầm",
    "vô trách nhiệm",
    "phung phí",
    "hoang phí",
    "kém kỷ luật",
    "thiếu kỷ luật",
    "thói quen xấu",
)
# AI không thay user quyết định: chỉ được nói "nếu bạn xác nhận, app sẽ…".
CLAIMED_ACTIONS: tuple[str, ...] = (
    "tôi đã điều chỉnh",
    "tôi đã cập nhật",
    "tôi đã thay đổi",
    "tôi đã tăng",
    "tôi đã áp dụng",
    "đã được điều chỉnh",
    "đã điều chỉnh ngân sách",
    "đã điều chỉnh budget",
    "đã cập nhật ngân sách",
    "đã cập nhật budget",
    "đã tăng ngân sách",
    "đã tăng budget",
    "app đã",
)
# Chỉ verdict `adjust_budget` mới được gợi ý nâng mức ngân sách.
RAISE_SUGGESTIONS: tuple[str, ...] = (
    "nên tăng ngân sách",
    "hãy tăng ngân sách",
    "cân nhắc tăng ngân sách",
    "có thể tăng ngân sách",
    "đề xuất tăng ngân sách",
    "tăng ngân sách lên",
    "nâng ngân sách",
    "nên tăng budget",
    "hãy tăng budget",
    "cân nhắc tăng budget",
    "có thể tăng budget",
    "tăng budget lên",
    "nâng budget",
    "nâng mức ngân sách",
    "điều chỉnh ngân sách lên",
)


# Tên trường / mã verdict (`cv_pct`, `adjust_budget`…) không được lộ ra văn bản cho user.
_TECHNICAL_NAME_RE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


# ---------- số liệu ----------


def evidence_payload(evidence: BudgetAdviceEvidence) -> dict[str, Any]:
    """Evidence dạng JSON không có ID — nguồn duy nhất cho prompt và tập số được phép."""
    return strip_ids(evidence.model_dump(mode="json"))


def allowed_numbers(evidence: BudgetAdviceEvidence) -> set[Decimal]:
    return review_narrative.collect_numbers(evidence_payload(evidence))


def prompt_numbers(evidence: BudgetAdviceEvidence) -> list[str]:
    values = sorted(allowed_numbers(evidence))
    return [f"{int(v):,}".replace(",", ".") if v == v.to_integral() else str(v) for v in values]


def _numbers_in(*texts: str | None) -> set[Decimal]:
    return {v for text in texts if text for _, v in extract_numbers(text)}


# ---------- kiểm tra ----------


def _fields(out: BudgetAdviceExplanation) -> list[tuple[str, str]]:
    items = [("observation", out.observation), ("explanation", out.explanation)]
    if out.action:
        items.append(("action", out.action))
    return items


def validate_explanation(
    out: BudgetAdviceExplanation,
    verdict: AdviceVerdict,
    evidence: BudgetAdviceEvidence,
    allowed: set[Decimal] | None = None,
) -> list[str]:
    """Danh sách vấn đề (rỗng = hợp lệ)."""
    allowed = allowed if allowed is not None else allowed_numbers(evidence)
    problems: list[str] = []
    if not out.observation.strip():
        problems.append("observation đang trống")
    if not out.explanation.strip():
        problems.append("explanation đang trống")
    if verdict != "on_track" and not (out.action and out.action.strip()):
        problems.append("thiếu action (tầng 3: gợi ý có điều kiện)")
    if out.action and not review_narrative.has_conditional(out.action):
        problems.append(
            "action phải là gợi ý có điều kiện (dùng 'nếu bạn xác nhận…' / 'bạn có thể cân nhắc…')"
        )

    phrases = BANNED_PHRASES + CLAIMED_ACTIONS
    if verdict != "adjust_budget":
        phrases += RAISE_SUGGESTIONS
    for name, text in _fields(out):
        for phrase in phrases:
            if review_narrative.contains_phrase(text, phrase):
                problems.append(f"{name} chứa cụm từ không được dùng: “{phrase}”")
        if technical := sorted(set(_TECHNICAL_NAME_RE.findall(text))):
            problems.append(
                f"{name} chứa tên trường / mã kỹ thuật {', '.join(technical)} — hãy viết tiếng Việt"
            )
        for raw, value in extract_numbers(text):
            if value not in allowed:
                problems.append(f"{name} có số “{raw}” không có trong evidence")

    if verdict == "adjust_budget" and evidence.proposed_planned_amount is not None:
        proposed = evidence.proposed_planned_amount
        if Decimal(proposed) not in _numbers_in(out.explanation, out.action):
            problems.append(
                f"explanation hoặc action cần nêu mức planned đề xuất {format_vnd(proposed)}"
            )
    if verdict == "one_off" and evidence.one_off_transaction is not None:
        tx = evidence.one_off_transaction
        if Decimal(tx.amount) not in _numbers_in(out.observation, out.explanation):
            problems.append(
                f"observation hoặc explanation cần nêu giao dịch ngoại lệ “{tx.note or ''}” "
                f"{format_vnd(tx.amount)} (khoản một lần)"
            )
    return problems


# ---------- template ----------


def _month(d: date) -> str:
    return f"tháng {d.month:02d}/{d.year}"


def _dm(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _tx_label(t: AdviceTransaction) -> str:
    return f"“{t.note}”" if t.note else t.category_name


def _observation(e: BudgetAdviceEvidence) -> str:
    head = f"{e.allocation_label} {_month(e.month)}: thực chi {format_vnd(e.actual_amount)}"
    if e.over_amount > 0:
        base = (
            f"vùng an toàn {format_vnd(e.threshold_amount)}"
            if e.comfort_high_used
            else f"kế hoạch {format_vnd(e.planned_amount)}"
        )
        text = f"{head}, vượt {format_vnd(e.over_amount)} so với {base}."
    else:
        text = f"{head} / kế hoạch {format_vnd(e.planned_amount)}"
        if e.comfort_high_used and e.actual_amount > e.planned_amount:
            text += f", vẫn trong vùng an toàn tới {format_vnd(e.threshold_amount)}"
        text += "."
    if not e.month_complete:
        text += f" Tháng chưa kết thúc — số liệu tính đến {_dm(e.as_of)}."
    return text


def _history_text(e: BudgetAdviceEvidence) -> str:
    return " / ".join(format_vnd(h.actual) for h in e.history_actuals)


def _one_off(e: BudgetAdviceEvidence) -> tuple[str, str]:
    t = e.one_off_transaction
    assert t is not None
    if e.rule == "one_off_irregular":
        reason = (
            f"Phần lớn phần vượt đến từ khoản bất thường {_tx_label(t)} {format_vnd(t.amount)} "
            f"({_dm(t.occurred_on)})"
        )
    else:
        share = e.single_transaction_share_pct
        reason = (
            f"Phần lớn phần vượt đến từ một giao dịch đơn lẻ {_tx_label(t)} "
            f"{format_vnd(t.amount)} ({_dm(t.occurred_on)}"
            + (f", {format_pct(share)} phần vượt)" if share is not None else ")")
        )
    explanation = (
        f"{reason} — đây là khoản một lần, không nhất thiết phản ánh nhu cầu chi tiêu thường "
        "xuyên nên chưa cần đổi mức ngân sách."
    )
    action = (
        "Nếu khoản này đã được tính trước hoặc đã xử lý xong, bạn có thể bỏ qua tư vấn này và "
        "giữ nguyên ngân sách."
    )
    return explanation, action


def _adjust_behavior(e: BudgetAdviceEvidence) -> tuple[str, str]:
    if e.rule == "insufficient_history":
        explanation = (
            f"Mới có {e.history_months} tháng có dữ liệu (cần {e.min_history_months} tháng) nên "
            "chưa đủ căn cứ để kết luận mức ngân sách này thấp hơn nhu cầu thực tế."
        )
    else:
        detail = (
            "không phải tháng nào cũng vượt kế hoạch"
            if not e.all_over_planned
            else f"mức chi còn dao động (hệ số biến thiên {format_pct(e.cv_pct or 0)}, ngưỡng "
            f"ổn định {format_pct(e.stable_cv_threshold_pct)})"
        )
        explanation = (
            f"Chi {e.allocation_label} {e.min_history_months} tháng gần nhất: {_history_text(e)} — "
            f"{detail}, nên chưa đủ ổn định để kết luận ngân sách đặt thấp."
        )
    action = (
        f"Nếu bạn muốn, bạn có thể xem lại các khoản {e.allocation_label} tháng này và theo dõi "
        "thêm trước khi quyết định đổi ngân sách."
    )
    return explanation, action


def _adjust_budget(e: BudgetAdviceEvidence) -> tuple[str, str]:
    proposed = e.proposed_planned_amount
    assert proposed is not None
    explanation = (
        f"{e.min_history_months} tháng gần nhất đều vượt kế hoạch và khá ổn định: "
        f"{_history_text(e)} (hệ số biến thiên {format_pct(e.cv_pct or 0)}). Mức "
        f"{format_vnd(e.planned_amount)} có vẻ thấp hơn mức chi thực tế gần đây."
    )
    action = (
        f"Nếu bạn xác nhận, app sẽ đặt ngân sách {e.allocation_label} tháng sau thành "
        f"{format_vnd(proposed)} (trung vị {e.min_history_months} tháng, làm tròn). Bạn cũng có "
        "thể giữ nguyên và xem lại thói quen chi."
    )
    return explanation, action


def template_explanation(
    verdict: AdviceVerdict, evidence: BudgetAdviceEvidence, reason: str | None = None
) -> AdviceNarrative:
    """Văn bản theo verdict từ evidence (không dùng AI). `reason` = mã lỗi AI nếu là dự phòng."""
    if verdict == "one_off":
        explanation, action = _one_off(evidence)
    elif verdict == "adjust_behavior":
        explanation, action = _adjust_behavior(evidence)
    elif verdict == "adjust_budget":
        explanation, action = _adjust_budget(evidence)
    else:
        explanation = "Mức chi đang nằm trong kế hoạch nên chưa cần điều chỉnh ngân sách."
        action = "Nếu bạn muốn, bạn có thể giữ nguyên mức ngân sách này cho tháng tới."
    return AdviceNarrative(
        observation=_observation(evidence),
        explanation=explanation,
        action=action,
        tone="neutral",
        generated_by="template",
        fallback_reason=reason,
    )


def join_text(narrative: BudgetAdviceExplanation) -> str:
    """Cột `budget_advice.explanation`: 3 tầng nối thành 1 đoạn."""
    return " ".join(
        p.strip() for p in (narrative.observation, narrative.explanation, narrative.action) if p
    )
