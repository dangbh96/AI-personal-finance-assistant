"""Viết explanation cho Budget advice (Phase 8) bằng model fast — chỉ diễn giải evidence.

Verdict + evidence do `services/advisor_rules` tính sẵn (ADR-005); model không quyết định gì.
Output được `services/advice_narrative.validate_explanation` kiểm tra (số ⊆ evidence, giọng văn,
không gợi ý tăng budget khi không phải `adjust_budget`…); sai → model sửa 1 lần
(`openai_client.structured_completion`), vẫn sai / AI lỗi → template deterministic.
Verdict `on_track` dùng template luôn (không cần AI).
"""

import json
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from app.ai import openai_client
from app.ai.openai_client import AIUnavailable, OutputValidationError
from app.models.enums import AdviceVerdict
from app.schemas.budget_advice import AdviceNarrative, BudgetAdviceEvidence, BudgetAdviceExplanation
from app.services import advice_narrative

PROMPT_FILE = Path(__file__).parent / "prompts" / "budget_advice_explanation.v1.md"
TASK = "budget_advice_explanation"
TIMEOUT_SECONDS = 30.0
MAX_PARALLEL = 4

_GUIDES: dict[str, str] = {
    "adjust_budget": (
        "   - `explanation`: các tháng trong `history_actuals` đều vượt kế hoạch và khá ổn định "
        "(`cv_pct` ≤ `stable_cv_threshold_pct`) — mức `planned_amount` có vẻ thấp hơn mức chi "
        "thực tế gần đây. Nêu các con số trong `history_actuals`.\n"
        "   - `action`: **bắt buộc** nêu `proposed_planned_amount` (trung vị các tháng, đã làm "
        'tròn), ví dụ "Nếu bạn xác nhận, app sẽ đặt ngân sách Ăn uống tháng sau thành '
        '4.500.000 ₫." Có thể thêm: bạn cũng có thể giữ nguyên và xem lại thói quen chi.'
    ),
    "one_off": (
        "   - `explanation`: **bắt buộc** nêu giao dịch ngoại lệ `one_off_transaction` (ghi chú "
        "`note` + số tiền `amount`), nói rõ đây là khoản một lần / bất thường, không nhất thiết "
        "phản ánh nhu cầu chi tiêu thường xuyên.\n"
        "   - **Không** gợi ý tăng hay nâng ngân sách.\n"
        '   - `action`: ví dụ "Nếu khoản này đã được tính trước, bạn có thể bỏ qua tư vấn này '
        'và giữ nguyên ngân sách."'
    ),
    "adjust_behavior": (
        "   - `explanation`: nếu `rule` = insufficient_history → mới có `history_months` tháng "
        "dữ liệu (cần `min_history_months`) nên chưa đủ căn cứ để kết luận mức ngân sách thấp "
        "hơn nhu cầu. Nếu `rule` = unstable_overspend → các tháng trong `history_actuals` không "
        "phải tháng nào cũng vượt kế hoạch (`all_over_planned` = false) hoặc còn dao động "
        "(`cv_pct` > `stable_cv_threshold_pct`) nên chưa đủ ổn định để kết luận ngân sách đặt "
        "thấp; nhịp chi tháng này là điều đáng xem lại.\n"
        "   - **Không** gợi ý tăng hay nâng ngân sách.\n"
        '   - `action`: ví dụ "Nếu bạn muốn, bạn có thể xem lại các khoản chi của dòng này '
        'tháng này trước khi quyết định đổi ngân sách."'
    ),
    "on_track": (
        "   - `explanation`: thực chi đang nằm trong kế hoạch, chưa cần điều chỉnh.\n"
        "   - **Không** gợi ý tăng hay nâng ngân sách."
    ),
}


@cache
def _prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def build_messages(
    verdict: AdviceVerdict, evidence: BudgetAdviceEvidence
) -> list[openai_client.Message]:
    payload = json.dumps(advice_narrative.evidence_payload(evidence), ensure_ascii=False, indent=1)
    system = (
        _prompt_template()
        .replace("{{verdict}}", verdict)
        .replace("{{verdict_label}}", advice_narrative.VERDICT_LABELS[verdict])
        .replace("{{verdict_guide}}", _GUIDES[verdict])
        .replace("{{evidence_json}}", payload)
        .replace("{{allowed_numbers}}", ", ".join(advice_narrative.prompt_numbers(evidence)))
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Viết giải thích cho tư vấn dòng “{evidence.allocation_label}” "
            f"tháng {evidence.month.month:02d}/{evidence.month.year}.",
        },
    ]


def _call_model(
    messages: list[openai_client.Message],
    verdict: AdviceVerdict,
    evidence: BudgetAdviceEvidence,
) -> tuple[AdviceNarrative, str]:
    allowed = advice_narrative.allowed_numbers(evidence)

    def validate(out: BudgetAdviceExplanation) -> None:
        problems = advice_narrative.validate_explanation(out, verdict, evidence, allowed)
        if problems:
            raise OutputValidationError(
                "; ".join(problems) + ". Chỉ dùng số có trong evidence, giữ giọng văn trung lập"
            )

    out, model = openai_client.structured_completion(
        BudgetAdviceExplanation,
        messages,
        task=TASK,
        model=openai_client.model_fast(),
        timeout=TIMEOUT_SECONDS,
        validate=validate,
    )
    return AdviceNarrative(**out.model_dump(), generated_by="ai"), model


def write_explanation(
    verdict: AdviceVerdict, evidence: BudgetAdviceEvidence
) -> tuple[AdviceNarrative, str]:
    """`(narrative, model)`; AI lỗi / output không qua kiểm tra → template (`fallback_template`)."""
    if verdict == "on_track":
        return (
            advice_narrative.template_explanation(verdict, evidence),
            advice_narrative.TEMPLATE_MODEL,
        )
    try:
        return _call_model(build_messages(verdict, evidence), verdict, evidence)
    except AIUnavailable as exc:
        return (
            advice_narrative.template_explanation(verdict, evidence, reason=exc.code),
            advice_narrative.FALLBACK_MODEL,
        )


def write_explanations(
    items: Sequence[tuple[AdviceVerdict, BudgetAdviceEvidence]],
) -> list[tuple[AdviceNarrative, str]]:
    """Nhiều advice — gọi model song song (tối đa `MAX_PARALLEL`), giữ thứ tự đầu vào."""
    if len(items) <= 1 or MAX_PARALLEL <= 1:
        return [write_explanation(v, e) for v, e in items]
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        return list(pool.map(lambda item: write_explanation(*item), items))
