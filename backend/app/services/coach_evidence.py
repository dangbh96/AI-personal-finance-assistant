"""Bảng "Dữ liệu đã dùng" và tóm tắt kết quả tool cho Financial Coach — deterministic.

- `evidence_rows(tool, output)`: các dòng số liệu (nhãn, kỳ, chỉ số, số tiền) rút từ output tool.
- `select_evidence(calls, answer)`: giữ các dòng có số tiền được câu trả lời trích dẫn, đánh mã
  E1, E2… theo thứ tự tool được gọi; trả kèm mã evidence của từng lần gọi (cho tool trace).
- `summarize_result(tool, output)`: mô tả ngắn + số dòng kết quả cho tool trace.
- `select_citations(calls, answer)` (Phase 16): đoạn kiến thức được trích trong mục "Nguồn:".
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.coach import (
    BudgetAdviceOutput,
    BudgetStatusOutput,
    CategoryTrendOutput,
    CitationItem,
    EvidenceItem,
    GetGoalsOutput,
    KnowledgeToolItem,
    RecentReviewsOutput,
    SearchKnowledgeOutput,
    SearchTransactionsOutput,
    SpendingSummaryOutput,
)
from app.services import coach_guard
from app.services.insight_service import SPENDING_TYPE_LABELS
from app.services.review_narrative import extract_numbers

MAX_EVIDENCE_ROWS = 20


@dataclass(frozen=True)
class EvidenceRow:
    tool: str
    label: str
    period: str
    metric: str
    amount: int


def _month(d: date) -> str:
    return f"{d:%m/%Y}"


def _range(a: date, b: date) -> str:
    if a.year == b.year:
        return f"{a:%d/%m}–{b:%d/%m/%Y}"
    return f"{a:%d/%m/%Y}–{b:%d/%m/%Y}"


def _month_key_label(key: str) -> str:
    year, month = key.split("-")
    return f"{month}/{year}"


def evidence_rows(tool: str, output: BaseModel) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []

    def add(label: str, period: str, metric: str, amount: int | None) -> None:
        if amount is not None:
            rows.append(EvidenceRow(tool, label, period, metric, amount))

    if isinstance(output, SpendingSummaryOutput):
        period = _range(output.from_date, output.to_date)
        add("Tất cả", period, "Tổng thu", output.income_total)
        add("Tất cả", period, "Tổng chi", output.expense_total)
        add("Tất cả", period, "Còn lại (thu − chi)", output.net)
        for i in output.items:
            label = i.category_name or SPENDING_TYPE_LABELS.get(i.spending_type or "", "Khác")
            add(label, period, "Tổng chi", i.total)
    elif isinstance(output, CategoryTrendOutput):
        for i in output.items:
            for key, total in i.totals_by_month.items():
                add(i.category_name, _month_key_label(key), "Chi tiêu", total)
            last = _month_key_label(output.months[-1])
            add(i.category_name, last, "Chênh lệch so với tháng trước", i.delta_vs_previous)
            add(i.category_name, f"{len(output.months)} tháng", "Trung bình / tháng", i.average)
            add(i.category_name, f"{len(output.months)} tháng", "Độ biến động", i.volatility)
            if i.irregular_total:
                add(
                    i.category_name,
                    f"{len(output.months)} tháng",
                    "Khoản bất thường",
                    i.irregular_total,
                )
    elif isinstance(output, BudgetStatusOutput) and output.available:
        period = _month(output.month)
        add("Tổng chi tiêu", period, "Ngân sách", output.expense_planned)
        add("Tổng chi tiêu", period, "Thực chi", output.expense_actual)
        add("Tổng chi tiêu", period, "Chênh lệch", output.expense_variance)
        add("Ngoài ngân sách", period, "Thực chi", output.unbudgeted_actual)
        for line in output.lines:
            add(line.label, period, "Ngân sách", line.planned)
            add(line.label, period, "Thực chi", line.actual)
            if line.variance:
                add(line.label, period, "Chênh lệch", line.variance)
            if line.top_contributor_amount is not None:
                note = line.top_contributor_note or "không ghi chú"
                add(line.label, period, f"Giao dịch lớn nhất ({note})", line.top_contributor_amount)
    elif isinstance(output, BudgetAdviceOutput):
        for a in output.items:
            period = _month(a.month)
            add(a.label, period, "Ngân sách", a.planned_amount)
            add(a.label, period, "Thực chi", a.actual_amount)
            add(a.label, period, "Chênh lệch", a.variance)
            add(a.label, period, "Ngân sách đề xuất", a.proposed_planned_amount)
    elif isinstance(output, RecentReviewsOutput):
        for r in output.items:
            label = "Review tháng" if r.kind == "monthly" else "Review tuần"
            period = _range(r.period_start, r.period_end)
            add(label, period, "Tổng thu", r.income)
            add(label, period, "Tổng chi", r.expense)
            for c in r.top_categories:
                add(c.category_name, period, "Chi tiêu", c.amount)
    elif isinstance(output, GetGoalsOutput):
        for g in output.active_goals:
            period = f"hạn {g.deadline:%d/%m/%Y}"
            add(g.name, period, "Số tiền mục tiêu", g.target_amount)
            add(g.name, period, "Đã có", g.current_amount)
            add(g.name, period, "Còn thiếu", g.remaining_amount)
            add(g.name, period, "Nên để dành / tháng", g.suggested_monthly_saving)
        if output.active_goals:
            add(
                "Mọi mục tiêu đang thực hiện",
                "mỗi tháng",
                "Tổng nên để dành / tháng",
                output.total_suggested_monthly_saving,
            )
    elif isinstance(output, SearchTransactionsOutput):
        if output.from_date and output.to_date:
            span = _range(output.from_date, output.to_date)
        else:
            span = "mọi thời gian"
        for item in output.items:
            label = item.note or item.category_name
            metric = "Thu" if item.direction == "income" else f"Chi · {item.category_name}"
            add(label, f"{item.occurred_on:%d/%m/%Y}", metric, item.amount)
        if output.items:
            add(f"Kết quả tìm “{output.query}”", span, "Tổng chi", output.expense_total)
            if output.income_total:
                add(f"Kết quả tìm “{output.query}”", span, "Tổng thu", output.income_total)
    return rows


def answer_amounts(answer: str) -> set[Decimal]:
    return {abs(v) for _, v in extract_numbers(answer)}


def select_evidence(
    calls: Sequence[tuple[str, BaseModel | None]], answer: str
) -> tuple[list[EvidenceItem], list[list[str]]]:
    """Dòng evidence có số tiền xuất hiện trong câu trả lời (≥ 1.000 đồng hoặc 0 không tính).

    Trả `(evidence, refs_theo_lần_gọi)` — `refs_theo_lần_gọi[i]` là mã của lần gọi thứ i.
    """
    cited = {v for v in answer_amounts(answer) if v >= 1000}
    evidence: list[EvidenceItem] = []
    refs: list[list[str]] = []
    seen: set[tuple[str, str, str, int]] = set()
    for tool, output in calls:
        call_refs: list[str] = []
        for row in evidence_rows(tool, output) if output is not None else []:
            key = (row.label, row.period, row.metric, row.amount)
            if Decimal(abs(row.amount)) not in cited or key in seen:
                continue
            if len(evidence) >= MAX_EVIDENCE_ROWS:
                break
            seen.add(key)
            ref = f"E{len(evidence) + 1}"
            evidence.append(EvidenceItem(ref=ref, **row.__dict__))
            call_refs.append(ref)
        refs.append(call_refs)
    return evidence, refs


def all_evidence(calls: Sequence[tuple[str, BaseModel | None]]) -> list[EvidenceItem]:
    """Mọi dòng evidence (cho câu trả lời dự phòng)."""
    rows = [r for tool, out in calls if out is not None for r in evidence_rows(tool, out)]
    return [EvidenceItem(ref=f"E{i + 1}", **r.__dict__) for i, r in enumerate(rows)]


def summarize_result(output: BaseModel) -> tuple[str, int]:
    if isinstance(output, SpendingSummaryOutput):
        n = len(output.items)
        unit = "danh mục" if output.group_by == "category" else "loại chi tiêu"
        return f"{n} {unit} · {_range(output.from_date, output.to_date)}", n
    if isinstance(output, CategoryTrendOutput):
        n = len(output.items)
        span = f"{_month_key_label(output.months[0])}–{_month_key_label(output.months[-1])}"
        return f"{n} danh mục · {len(output.months)} tháng ({span})", n
    if isinstance(output, BudgetStatusOutput):
        if not output.available:
            return f"Không có ngân sách đang theo dõi tháng {_month(output.month)}", 0
        n = len(output.lines)
        return f"{n} dòng ngân sách · tháng {_month(output.month)}", n
    if isinstance(output, BudgetAdviceOutput):
        n = len(output.items)
        if not n:
            return "Chưa có tư vấn điều chỉnh", 0
        return f"{n} tư vấn · tháng {_month(output.month)}" if output.month else f"{n} tư vấn", n
    if isinstance(output, RecentReviewsOutput):
        n = len(output.items)
        return (f"{n} review" if n else "Chưa có review"), n
    if isinstance(output, GetGoalsOutput):
        n = len(output.active_goals)
        return (f"{n} mục tiêu đang thực hiện" if n else "Chưa có mục tiêu đang thực hiện"), n
    if isinstance(output, SearchTransactionsOutput):
        n = output.result_count
        return (f"{n} giao dịch khớp “{output.query}”" if n else "Không tìm thấy giao dịch"), n
    if isinstance(output, SearchKnowledgeOutput):
        n = len(output.results)
        if not n:
            return "Không tìm thấy nguồn kiến thức phù hợp", 0
        titles = ", ".join(dict.fromkeys(r.title for r in output.results))
        return f"Đã tra kiến thức: {titles} ({n} đoạn)", n
    return "Đã đọc dữ liệu", 0


SNIPPET_CHARS = 600


def knowledge_items(calls: Sequence[tuple[str, BaseModel | None]]) -> list[KnowledgeToolItem]:
    """Các đoạn kiến thức (không trùng) trả về từ mọi lần gọi `search_knowledge`."""
    seen: dict[object, KnowledgeToolItem] = {}
    for _, output in calls:
        if isinstance(output, SearchKnowledgeOutput):
            for item in output.results:
                seen.setdefault(item.chunk_id, item)
    return list(seen.values())


def select_citations(
    calls: Sequence[tuple[str, BaseModel | None]], answer: str
) -> list[CitationItem]:
    """Nguồn hiển thị kèm câu trả lời: đoạn được nhắc trong mục "Nguồn:" (khớp tiêu đề / đường
    dẫn); có mục Nguồn mà không khớp đoạn nào → không trả nguồn nào (không gắn nguồn sai)."""
    items = knowledge_items(calls)
    if not items or not coach_guard.source_lines(answer):
        return []
    indexes = coach_guard.cited_indexes(answer, [i.title for i in items], [i.source for i in items])
    cited = [items[i] for i in indexes]
    return [
        CitationItem(
            ref=f"S{n + 1}",
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            title=item.title,
            heading=item.heading,
            source=item.source,
            citation=item.citation,
            snippet=item.content[:SNIPPET_CHARS].rstrip()
            + ("…" if len(item.content) > SNIPPET_CHARS else ""),
            score=item.score,
        )
        for n, item in enumerate(cited)
    ]
