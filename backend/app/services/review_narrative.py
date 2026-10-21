"""Kiểm tra narrative review và bản tóm tắt dự phòng — deterministic, không gọi AI (ADR-005).

- `allowed_numbers(metrics)`: mọi con số narrative được phép dùng (tiền, %, số lượng, ngày/tháng/
  năm, số trong ghi chú / tên danh mục) — lấy từ metrics đã tính sẵn.
- `extract_numbers(text)`: đọc số kiểu Việt Nam ("1.180.000", "18%", "0,5 triệu", "620k").
- `validate_narrative`: số ⊆ allowed, không có cụm từ cấm, đủ 3 tầng, action có điều kiện; tháng:
  chi tăng chủ yếu do khoản bất thường thì phải nêu khoản đó.
- `fallback_narrative`: narrative dạng template từ metrics (luôn qua được `validate_narrative`).
"""

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.text import strip_accents
from app.schemas.review import (
    MonthlyReviewMetrics,
    ReviewMetrics,
    ReviewNarrative,
    ReviewNarrativeOutput,
)
from app.services.money import format_vnd

FALLBACK_MODEL = "fallback_template"

# Giọng văn không phán xét (docs/architecture/ai-architecture.md § 2). Review không tự đưa ra kết
# luận "ngân sách sai / hành vi sai" — việc đó thuộc Budget advisor (Phase 8).
BANNED_PHRASES: tuple[str, ...] = (
    "bạn tiêu quá nhiều",
    "lãng phí",
    "bạn phải",
    "bạn nên ngay lập tức",
    "vô trách nhiệm",
    "phung phí",
    "hoang phí",
    "kém kỷ luật",
    "thiếu kỷ luật",
    "thói quen xấu",
    "ngân sách sai",
    "đặt sai ngân sách",
    "ngân sách đặt sai",
    "ngân sách không hợp lý",
    "ngân sách chưa hợp lý",
    "adjust_budget",
    "adjust_behavior",
)
# Action phải là gợi ý có điều kiện, không ra lệnh.
CONDITIONAL_MARKERS: tuple[str, ...] = ("nếu", "có thể", "cân nhắc", "thử")

_MULTIPLIERS = {
    "tỷ": Decimal(1_000_000_000),
    "triệu": Decimal(1_000_000),
    "tr": Decimal(1_000_000),
    "nghìn": Decimal(1_000),
    "ngàn": Decimal(1_000),
    "k": Decimal(1_000),
}
_NUMBER_RE = re.compile(
    r"(?<![\w.,])"
    r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+\.\d{1,2}(?!\d)|\d+(?:,\d+)?)"
    r"(?:\s*(tỷ|triệu|tr|nghìn|ngàn|k)(?!\w))?",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_PERIOD_WORDS = {"week": "tuần", "month": "tháng"}


# ---------- số liệu ----------


def _parse_number(raw: str, unit: str | None) -> Decimal | None:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
        text = raw.replace(".", "").replace(",", ".")
    else:
        text = raw.replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if unit:
        value *= _MULTIPLIERS[unit.lower()]
    return value.normalize()


def extract_numbers(text: str) -> list[tuple[str, Decimal]]:
    """`[(chuỗi gốc, giá trị)]` của mọi số trong văn bản.

    >>> [v for _, v in extract_numbers("chi 1.180.000 ₫, tăng 18%, 0,5 triệu")]
    [Decimal('1.18E+6'), Decimal('18'), Decimal('5E+5')]
    """
    found = []
    for match in _NUMBER_RE.finditer(text):
        value = _parse_number(match.group(1), match.group(2))
        if value is not None:
            found.append((match.group(0).strip(), value))
    return found


def _collect(node: Any, out: set[Decimal]) -> None:
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, int | float):
        out.add(abs(Decimal(str(node))).normalize())
    elif isinstance(node, str):
        if m := _ISO_DATE_RE.match(node):
            out.update(Decimal(int(part)).normalize() for part in m.groups())
        else:
            out.update(v for _, v in extract_numbers(node))
    elif isinstance(node, dict):
        for value in node.values():
            _collect(value, out)
    elif isinstance(node, list):
        out.add(Decimal(len(node)))
        for value in node:
            _collect(value, out)


# UUID / khoá kỹ thuật không phải "số liệu" (và có thể chứa chữ số) → bỏ khi gom số / dựng prompt.
_ID_KEYS = frozenset({"id", "key", "icon"})


def _is_id_key(key: str) -> bool:
    return key in _ID_KEYS or key.endswith(("_id", "_ids"))


def strip_ids(node: Any) -> Any:
    """Bỏ mọi khoá `id`, `key`, `icon`, `*_id`, `*_ids` (đệ quy) khỏi metrics đã dump JSON."""
    if isinstance(node, dict):
        return {k: strip_ids(v) for k, v in node.items() if not _is_id_key(k)}
    if isinstance(node, list):
        return [strip_ids(v) for v in node]
    return node


def metrics_payload(metrics: ReviewMetrics) -> dict[str, Any]:
    """Metrics dạng JSON (không có ID) — nguồn duy nhất cho prompt và tập số được phép."""
    return strip_ids(metrics.model_dump(mode="json"))


def allowed_numbers(metrics: ReviewMetrics) -> set[Decimal]:
    """Mọi giá trị số có trong metrics + highlights (giá trị tuyệt đối)."""
    out: set[Decimal] = {Decimal(0)}
    _collect(metrics_payload(metrics), out)
    return out


def prompt_numbers(metrics: ReviewMetrics) -> list[str]:
    """Danh sách số được phép (đã định dạng kiểu Việt Nam) để đưa vào prompt."""
    values = sorted(allowed_numbers(metrics))
    return [f"{int(v):,}".replace(",", ".") if v == v.to_integral() else str(v) for v in values]


# ---------- kiểm tra ----------


def _fold(text: str) -> str:
    return " ".join(strip_accents(text).lower().split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_fold(phrase))}(?!\w)", _fold(text)) is not None


def _has_conditional(text: str) -> bool:
    # "thử" chỉ so khớp có dấu: bỏ dấu sẽ trùng "thu" (thu nhập).
    lowered = unicodedata.normalize("NFC", text).lower()
    return "thử" in lowered or any(
        _contains_phrase(text, m) for m in CONDITIONAL_MARKERS if m != "thử"
    )


def _texts(narrative: ReviewNarrativeOutput) -> list[tuple[str, str]]:
    items = [
        ("observation", narrative.observation),
        ("explanation", narrative.explanation),
        *((f"notice[{i}]", n) for i, n in enumerate(narrative.notice)),
        ("reflection_question", narrative.reflection_question),
    ]
    if narrative.action:
        items.append(("action", narrative.action))
    return items


def validate_narrative(
    narrative: ReviewNarrativeOutput, metrics: ReviewMetrics, allowed: set[Decimal] | None = None
) -> list[str]:
    """Danh sách vấn đề (rỗng = hợp lệ)."""
    allowed = allowed if allowed is not None else allowed_numbers(metrics)
    problems: list[str] = []

    for name, value in (
        ("observation", narrative.observation),
        ("explanation", narrative.explanation),
        ("reflection_question", narrative.reflection_question),
    ):
        if not value.strip():
            problems.append(f"{name} đang trống")
    if not narrative.notice or any(not n.strip() for n in narrative.notice):
        problems.append("notice cần 1–3 ý, không ý nào trống")
    has_activity = metrics.expense > 0 or metrics.income > 0
    if has_activity and not (narrative.action and narrative.action.strip()):
        problems.append("thiếu action (tầng 3: gợi ý có điều kiện)")
    if narrative.action and not _has_conditional(narrative.action):
        problems.append(
            "action phải là gợi ý có điều kiện (dùng 'nếu bạn muốn…' / 'bạn có thể cân nhắc…')"
        )

    for name, text in _texts(narrative):
        for phrase in BANNED_PHRASES:
            if _contains_phrase(text, phrase):
                problems.append(f"{name} chứa cụm từ phán xét bị cấm: “{phrase}”")
        for raw, value in extract_numbers(text):
            if value not in allowed:
                problems.append(f"{name} có số “{raw}” không có trong metrics")
    if isinstance(metrics, MonthlyReviewMetrics):
        problems += _monthly_problems(narrative, metrics)
    return problems


def _monthly_problems(narrative: ReviewNarrativeOutput, m: MonthlyReviewMetrics) -> list[str]:
    """Chi tăng chủ yếu do khoản bất thường → phải nêu khoản đó (không quy kết thói quen)."""
    if m.increase_driver != "irregular" or not m.irregular_items:
        return []
    top = m.irregular_items[0]
    mentioned = {v for _, v in extract_numbers(f"{narrative.observation} {narrative.explanation}")}
    if Decimal(top.amount) in mentioned:
        return []
    return [
        f"chi tiêu tăng chủ yếu do khoản bất thường “{top.note or top.category_name}” "
        f"{format_vnd(top.amount)} — observation hoặc explanation cần nêu khoản này "
        "(khoản một lần, không phải thói quen)"
    ]


# ---------- bản dự phòng (template) ----------


def _dm(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def period_label(metrics: ReviewMetrics) -> str:
    """ "Tuần 12/10–18/10/2026" hoặc "Tháng 10/2026"."""
    if metrics.period == "month":
        return f"Tháng {metrics.period_start.month:02d}/{metrics.period_start.year}"
    return f"Tuần {_dm(metrics.period_start)}–{_dm(metrics.period_end)}/{metrics.period_end.year}"


def _observation(m: ReviewMetrics, word: str) -> str:
    if m.expense == 0 and m.income == 0:
        text = f"{period_label(m)} chưa có giao dịch nào được ghi."
    else:
        text = f"{period_label(m)} bạn chi {format_vnd(m.expense)}, thu {format_vnd(m.income)}."
        pct = m.expense_change_pct
        if pct is None:
            text += f" {word.capitalize()} trước chưa có khoản chi nào để so sánh."
        elif pct > 0:
            text += f" Chi tiêu cao hơn {word} trước {pct}% ({format_vnd(m.previous_expense)})."
        elif pct < 0:
            text += (
                f" Chi tiêu thấp hơn {word} trước {abs(pct)}% ({format_vnd(m.previous_expense)})."
            )
        else:
            text += f" Chi tiêu tương đương {word} trước."
    if not m.complete:
        text += f" {word.capitalize()} chưa kết thúc — số liệu tính đến {_dm(m.as_of)}."
    return text


def _explanation(m: ReviewMetrics, word: str) -> str:
    h = m.highlights
    if m.expense_change > 0 and h.top_increase is not None:
        c = h.top_increase
        text = (
            f"Phần tăng nhiều nhất đến từ {c.name}: {format_vnd(c.amount)}, "
            f"cao hơn {word} trước {format_vnd(c.change)}."
        )
    elif m.expense_change < 0 and h.top_decrease is not None:
        c = h.top_decrease
        text = (
            f"Khoản giảm nhiều nhất là {c.name}: {format_vnd(c.amount)}, "
            f"thấp hơn {word} trước {format_vnd(abs(c.change))}."
        )
    elif h.top_categories:
        c = h.top_categories[0]
        text = f"Danh mục chi nhiều nhất là {c.name}: {format_vnd(c.amount)}."
    else:
        return "Chưa có đủ dữ liệu chi tiêu để giải thích xu hướng."
    s = m.by_spending_type
    return (
        f"{text} Theo loại chi tiêu: thiết yếu {format_vnd(s.essential)}, "
        f"không thiết yếu {format_vnd(s.non_essential)}, bất thường {format_vnd(s.irregular)}."
    )


def _notice(m: ReviewMetrics, word: str) -> list[str]:
    h = m.highlights
    items = [
        f"{c.count} khoản “{c.label}”, tổng {format_vnd(c.total)}." for c in h.repeated_clusters[:2]
    ]
    if h.top_transactions:
        t = h.top_transactions[0]
        items.append(
            f"Khoản chi lớn nhất: “{t.note or t.category_name}” {format_vnd(t.amount)} "
            f"({t.category_name}, {_dm(t.occurred_on)})."
        )
    return items or [f"Chưa có khoản chi nào trong {word} này."]


def _action(m: ReviewMetrics, word: str) -> str | None:
    h = m.highlights
    if h.repeated_clusters:
        return (
            f"Nếu bạn muốn, bạn có thể xem lại các khoản “{h.repeated_clusters[0].label}” "
            "và đánh dấu khoản nào chưa thật sự đáng tiền."
        )
    if m.expense_change > 0 and h.top_increase is not None:
        return (
            f"Nếu bạn muốn, bạn có thể xem lại các khoản {h.top_increase.name} {word} này "
            "để quyết định khoản nào nên giữ."
        )
    if m.expense > 0 or m.income > 0:
        return f"Nếu bạn muốn, bạn có thể xem lại các khoản chi lớn nhất trong {word}."
    return None


def fallback_narrative(metrics: ReviewMetrics, reason: str | None) -> ReviewNarrative:
    """Narrative template từ metrics, dùng khi AI lỗi hoặc output không qua kiểm tra."""
    if isinstance(metrics, MonthlyReviewMetrics):
        return _monthly_fallback(metrics, reason)
    word = _PERIOD_WORDS[metrics.period]
    return ReviewNarrative(
        observation=_observation(metrics, word),
        explanation=_explanation(metrics, word),
        notice=_notice(metrics, word)[:3],
        action=_action(metrics, word),
        reflection_question=f"Có khoản nào trong {word} này bạn thấy không đáng tiền không?",
        tone="neutral",
        fallback_used=True,
        fallback_reason=reason,
    )


# ---------- bản dự phòng cho tháng (Phase 7) ----------

MONTHLY_REFLECTION_QUESTION = (
    "Điều gì trong tháng này bạn muốn giữ, và điều gì bạn muốn điều chỉnh cho tháng tới?"
)


def format_pct(value: float) -> str:
    """26.4 → "26,4%", 50.0 → "50%" (giá trị đã tính sẵn trong metrics)."""
    text = str(int(value)) if value == int(value) else f"{value:.1f}".replace(".", ",")
    return f"{text}%"


def _tx_label(note: str | None, category_name: str) -> str:
    return f"“{note}”" if note else category_name


def _monthly_observation(m: MonthlyReviewMetrics) -> str:
    label = period_label(m)
    if m.expense == 0 and m.income == 0:
        text = f"{label} chưa có giao dịch nào được ghi."
    else:
        text = f"{label} bạn thu {format_vnd(m.income)}, chi {format_vnd(m.expense)}"
        if m.savings_rate_pct is not None and m.saved >= 0:
            text += (
                f", còn lại {format_vnd(m.saved)} "
                f"(tỉ lệ tiết kiệm {format_pct(m.savings_rate_pct)})."
            )
        elif m.saved < 0:
            text += f", chi nhiều hơn thu {format_vnd(abs(m.saved))}."
        else:
            text += "."
        pct = m.expense_change_pct
        if pct is None:
            text += " Tháng trước chưa có khoản chi nào để so sánh."
        elif pct > 0:
            text += f" Chi tiêu cao hơn tháng trước {pct}% ({format_vnd(m.previous_expense)})."
        elif pct < 0:
            text += (
                f" Chi tiêu thấp hơn tháng trước {abs(pct)}% ({format_vnd(m.previous_expense)})."
            )
        else:
            text += " Chi tiêu tương đương tháng trước."
    if not m.complete:
        text += f" Tháng chưa kết thúc — số liệu tính đến {_dm(m.as_of)}."
    return text


def _breakdown_sentence(m: MonthlyReviewMetrics) -> str:
    s, p = m.by_spending_type, m.spending_type_pct
    parts = []
    for name, amount, pct in (
        ("thiết yếu", s.essential, p.essential),
        ("không thiết yếu", s.non_essential, p.non_essential),
        ("bất thường", s.irregular, p.irregular),
    ):
        share = f" ({format_pct(pct)})" if pct is not None else ""
        parts.append(f"{name} {format_vnd(amount)}{share}")
    return "Theo loại chi tiêu: " + ", ".join(parts) + "."


def _monthly_explanation(m: MonthlyReviewMetrics) -> str:
    h = m.highlights
    if m.increase_driver == "irregular" and m.irregular_items:
        t = m.irregular_items[0]
        text = (
            f"Phần lớn mức tăng đến từ khoản bất thường {_tx_label(t.note, t.category_name)} "
            f"{format_vnd(t.amount)} ({t.category_name}, {_dm(t.occurred_on)})."
        )
        pct = m.regular_expense_change_pct
        if pct is not None:
            if pct > 0:
                trend = f"cao hơn tháng trước {pct}%"
            elif pct < 0:
                trend = f"thấp hơn tháng trước {abs(pct)}%"
            else:
                trend = "tương đương tháng trước"
            text += f" Không tính khoản bất thường, chi thường xuyên {trend}."
    elif m.expense_change > 0 and h.top_increase is not None:
        c = h.top_increase
        text = (
            f"Phần tăng nhiều nhất đến từ {c.name}: {format_vnd(c.amount)}, "
            f"cao hơn tháng trước {format_vnd(c.change)}."
        )
    elif m.expense_change < 0 and h.top_decrease is not None:
        c = h.top_decrease
        text = (
            f"Khoản giảm nhiều nhất là {c.name}: {format_vnd(c.amount)}, "
            f"thấp hơn tháng trước {format_vnd(abs(c.change))}."
        )
    elif h.top_categories:
        c = h.top_categories[0]
        text = f"Danh mục chi nhiều nhất là {c.name}: {format_vnd(c.amount)}."
    else:
        return "Chưa có đủ dữ liệu chi tiêu để giải thích xu hướng."
    return f"{text} {_breakdown_sentence(m)}"


def _monthly_notice(m: MonthlyReviewMetrics) -> list[str]:
    items: list[str] = []
    if m.budget and m.budget.over_lines:
        line = m.budget.over_lines[0]
        items.append(
            f"{line.label} vượt ngân sách {format_vnd(line.variance)} "
            f"(thực chi {format_vnd(line.actual)} / kế hoạch {format_vnd(line.planned)})."
        )
    if m.irregular_items and m.increase_driver != "irregular":
        t = m.irregular_items[0]
        items.append(
            f"Khoản bất thường lớn nhất: {_tx_label(t.note, t.category_name)} "
            f"{format_vnd(t.amount)} ({t.category_name})."
        )
    if m.flagged_count:
        items.append(
            f"Trong các review tuần, bạn đã đánh dấu {m.flagged_count} khoản chưa đáng tiền, "
            f"tổng {format_vnd(m.flagged_total)}."
        )
    if m.highlights.repeated_clusters:
        c = m.highlights.repeated_clusters[0]
        items.append(f"{c.count} khoản “{c.label}”, tổng {format_vnd(c.total)}.")
    if m.highlights.top_transactions and not m.irregular_items:
        t = m.highlights.top_transactions[0]
        items.append(
            f"Khoản chi lớn nhất: {_tx_label(t.note, t.category_name)} {format_vnd(t.amount)} "
            f"({t.category_name}, {_dm(t.occurred_on)})."
        )
    return items[:3] or ["Chưa có khoản chi nào trong tháng này."]


def _monthly_action(m: MonthlyReviewMetrics) -> str | None:
    if m.budget and m.budget.over_lines:
        return (
            "Nếu bạn muốn, bạn có thể xem phần tư vấn điều chỉnh ngân sách để cân nhắc "
            "kế hoạch cho tháng tới."
        )
    if m.expense > 0 or m.income > 0:
        return (
            "Nếu bạn muốn, bạn có thể chọn một điểm muốn giữ và một điểm muốn điều chỉnh "
            "cho tháng tới."
        )
    return None


def _monthly_fallback(m: MonthlyReviewMetrics, reason: str | None) -> ReviewNarrative:
    return ReviewNarrative(
        observation=_monthly_observation(m),
        explanation=_monthly_explanation(m),
        notice=_monthly_notice(m),
        action=_monthly_action(m),
        reflection_question=MONTHLY_REFLECTION_QUESTION,
        tone="neutral",
        fallback_used=True,
        fallback_reason=reason,
    )
