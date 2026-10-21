"""Viết narrative review (What happened / Why / Notice / Action / Reflection) bằng model smart.

Input là metrics đã tính sẵn (deterministic); model chỉ diễn giải, không tính toán (ADR-005).
Việc kiểm tra số liệu / giọng văn và retry nằm ở `agents/review_graph`.
"""

import json
from functools import cache
from pathlib import Path

from app.ai import openai_client
from app.schemas.review import ReviewMetrics, ReviewNarrativeOutput
from app.services import review_narrative

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_FILES = {
    "week": PROMPTS_DIR / "review_narrative.v1.md",
    "month": PROMPTS_DIR / "review_narrative_month.v1.md",
}
TASK = "review_narrative"
TIMEOUT_SECONDS = 60.0
_PERIOD_WORDS = {"week": "tuần", "month": "tháng"}


@cache
def _prompt_template(period: str) -> str:
    return PROMPT_FILES[period].read_text(encoding="utf-8")


def metrics_for_prompt(metrics: ReviewMetrics) -> str:
    """Metrics JSON không kèm ID (bớt token, tránh nhầm số)."""
    return json.dumps(review_narrative.metrics_payload(metrics), ensure_ascii=False, indent=1)


def build_messages(metrics: ReviewMetrics) -> list[openai_client.Message]:
    word = _PERIOD_WORDS[metrics.period]
    system = (
        _prompt_template(metrics.period)
        .replace("{{period_word}}", word)
        .replace("{{period_label}}", review_narrative.period_label(metrics))
        .replace("{{metrics_json}}", metrics_for_prompt(metrics))
        .replace("{{allowed_numbers}}", ", ".join(review_narrative.prompt_numbers(metrics)))
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Viết review {word} {review_narrative.period_label(metrics)}.",
        },
    ]


def feedback_message(problems: list[str]) -> openai_client.Message:
    return {
        "role": "user",
        "content": "Bản vừa rồi chưa đạt kiểm tra tự động: "
        + "; ".join(problems)
        + ". Hãy viết lại toàn bộ JSON, chỉ dùng số có trong số liệu và giữ giọng văn trung lập.",
    }


def write_narrative(
    messages: list[openai_client.Message],
) -> tuple[ReviewNarrativeOutput, str]:
    """Một lượt gọi model; raise `AIUnavailable` nếu AI lỗi / chưa cấu hình."""
    return openai_client.structured_completion(
        ReviewNarrativeOutput,
        messages,
        task=TASK,
        model=openai_client.model_smart(),
        timeout=TIMEOUT_SECONDS,
    )
