"""Diễn giải kết quả What-if (Phase 17) bằng model fast — chỉ diễn giải `SimulationResult` đã tính.

Output được `services/simulator_narrative.validate` kiểm tra (số ⊆ kết quả, giọng văn, không gợi ý
vay / đầu tư, gợi ý có điều kiện); sai → model sửa 1 lần (`structured_completion`), vẫn sai / AI
lỗi / chưa cấu hình → `template_narrative` (không trả 503).
"""

import json
from functools import cache
from pathlib import Path

from app.ai import openai_client
from app.ai.openai_client import AIUnavailable, OutputValidationError
from app.schemas.simulator import SimulationNarrative, SimulationResult
from app.services import simulator_narrative
from app.services.review_narrative import strip_ids

PROMPT_FILE = Path(__file__).parent / "prompts" / "simulator_narrative.v1.md"
TASK = "simulator_narrative"
TIMEOUT_SECONDS = 30.0
TEMPLATE_MODEL = "template"


@cache
def _prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _prompt_numbers(result: SimulationResult) -> str:
    values = sorted(simulator_narrative.allowed_numbers(result))
    return ", ".join(format(v.normalize(), "f") for v in values)


def build_messages(result: SimulationResult) -> list[openai_client.Message]:
    payload = strip_ids(result.model_dump(mode="json", exclude={"narrative"}))
    system = (
        _prompt_template()
        .replace("{{result_json}}", json.dumps(payload, ensure_ascii=False, indent=1))
        .replace("{{allowed_numbers}}", _prompt_numbers(result))
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Diễn giải kết quả mô phỏng này giúp mình."},
    ]


def write_narrative(result: SimulationResult) -> tuple[SimulationNarrative, str, str]:
    """`(narrative, source "ai" | "template", model)`."""

    def validate(out: SimulationNarrative) -> None:
        problems = simulator_narrative.validate(out, result)
        if problems:
            raise OutputValidationError("; ".join(problems))

    try:
        out, model = openai_client.structured_completion(
            SimulationNarrative,
            build_messages(result),
            task=TASK,
            model=openai_client.model_fast(),
            timeout=TIMEOUT_SECONDS,
            validate=validate,
        )
        return out, "ai", model
    except AIUnavailable:
        return simulator_narrative.template_narrative(result), "template", TEMPLATE_MODEL
