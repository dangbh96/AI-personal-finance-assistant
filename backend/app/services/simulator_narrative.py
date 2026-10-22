"""Diễn giải kết quả mô phỏng (Phase 17) — phần deterministic: số được phép, kiểm tra, mẫu.

AI (`ai/simulator_writer`) chỉ viết câu chữ từ `SimulationResult` đã tính; mọi số phải nằm trong
kết quả, không phán xét / ra lệnh, không gợi ý vay / đầu tư. Lỗi / sai → `template_narrative`.
"""

import re
import unicodedata
from decimal import Decimal
from typing import Any

from app.schemas.simulator import SimulationNarrative, SimulationResult
from app.services import coach_guard, review_narrative
from app.services.money import format_vnd
from app.services.review_narrative import extract_numbers

DAYS_PER_MONTH = Decimal(30)
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
# Ngoài cụm cấm chung: không đẩy người dùng sang vay / đầu tư rủi ro.
RISKY_SUGGESTIONS: tuple[str, ...] = (
    "vay",
    "đầu tư",
    "chứng khoán",
    "cổ phiếu",
    "crypto",
    "tiền ảo",
    "thẻ tín dụng để",
)


def _date_parts(node: Any, out: set[Decimal]) -> None:
    """Ngày ISO trong kết quả (ngày hoàn thành, hạn…) → được trích ngày / tháng / năm."""
    if isinstance(node, dict):
        for value in node.values():
            _date_parts(value, out)
    elif isinstance(node, list):
        for value in node:
            _date_parts(value, out)
    elif isinstance(node, str) and (m := _ISO_DATE_RE.match(node)):
        out.update(Decimal(int(p)) for p in m.groups())


def allowed_numbers(result: SimulationResult) -> set[Decimal]:
    payload = result.model_dump(mode="json", exclude={"narrative"})
    allowed = coach_guard.allowed_numbers([payload], "", result.start_date)
    _date_parts(payload, allowed)
    allowed.add(DAYS_PER_MONTH)
    return allowed


def _texts(narrative: SimulationNarrative) -> list[str]:
    return [
        narrative.observation,
        narrative.explanation,
        narrative.action or "",
        *narrative.caveats,
    ]


def _has_term(text: str, term: str) -> bool:
    """So khớp có dấu, theo ranh giới từ ("vay" không khớp "vậy")."""
    lowered = unicodedata.normalize("NFC", text).lower()
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) is not None


def validate(narrative: SimulationNarrative, result: SimulationResult) -> list[str]:
    allowed = allowed_numbers(result)
    problems: list[str] = []
    full = "\n".join(_texts(narrative))
    invented = [raw for raw, value in extract_numbers(full) if abs(value) not in allowed]
    if invented:
        problems.append(
            "có số không nằm trong kết quả mô phỏng: "
            + ", ".join(f"“{r}”" for r in dict.fromkeys(invented))
        )
    for phrase in coach_guard.BANNED_PHRASES:
        if review_narrative.contains_phrase(full, phrase):
            problems.append(f"có cụm từ không được dùng: “{phrase}”")
    for term in RISKY_SUGGESTIONS:
        if _has_term(full, term):
            problems.append(f"không gợi ý vay / đầu tư: “{term}”")
    if narrative.action and not review_narrative.has_conditional(narrative.action):
        problems.append("gợi ý phải có điều kiện (“nếu bạn muốn…”, “có thể cân nhắc…”)")
    if len(narrative.caveats) > 3:
        problems.append("tối đa 3 lưu ý")
    return problems


def focus_goal(result: SimulationResult):
    """Mục tiêu bị ảnh hưởng nhiều nhất (|days_earlier| lớn nhất), ưu tiên priority cao."""
    candidates = [g for g in result.goal_impacts if g.days_earlier]
    if not candidates:
        return None
    return max(candidates, key=lambda g: (abs(g.days_earlier or 0), -g.priority))


def template_narrative(result: SimulationResult) -> SimulationNarrative:
    """Diễn giải không dùng AI — luôn qua `validate`."""
    changes = "; ".join(a.label for a in result.applied)
    delta = result.delta_monthly_savings
    if delta > 0:
        trend = f"tăng {format_vnd(delta)}"
    elif delta < 0:
        trend = f"giảm {format_vnd(-delta)}"
    else:
        trend = "không đổi"
    observation = (
        f"Với kịch bản: {changes}, số tiền để dành mỗi tháng {trend} — từ "
        f"{format_vnd(result.baseline_monthly_savings)} thành "
        f"{format_vnd(result.projected_monthly_savings)}."
    )
    parts = [
        f"{a.label}: {'+' if a.delta_monthly_savings > 0 else ''}"
        f"{format_vnd(a.delta_monthly_savings)} mỗi tháng."
        for a in result.applied
        if a.delta_monthly_savings
    ]
    goal = focus_goal(result)
    if goal is not None and goal.days_after is not None and goal.days_before is not None:
        direction = "sớm hơn" if (goal.days_earlier or 0) > 0 else "muộn hơn"
        parts.append(
            f"Mục tiêu “{goal.name}” đạt sau {goal.days_after} ngày thay vì {goal.days_before} "
            f"ngày — {direction} {abs(goal.days_earlier or 0)} ngày."
        )
    elif result.projected_monthly_savings <= 0 and result.goal_impacts:
        parts.append("Khi không còn tiền để dành, các mục tiêu chưa thể tiến triển.")
    explanation = " ".join(parts) or "Các thay đổi không làm đổi số tiền để dành mỗi tháng."
    action = (
        "Nếu bạn muốn thử thật, bạn có thể cân nhắc điều chỉnh ngân sách tháng tới cho phù hợp "
        "rồi theo dõi lại sau vài tuần."
        if delta > 0
        else "Nếu bạn muốn giữ tiến độ mục tiêu, bạn có thể cân nhắc thêm một thay đổi bù lại "
        "rồi mô phỏng lại."
        if delta < 0
        else None
    )
    caveats = [
        f"Mô phỏng dùng mức trung bình {result.baseline_months} tháng gần nhất, quy ước 1 tháng = "
        "30 ngày.",
        "Kết quả chỉ là mô phỏng, chưa thay đổi dữ liệu thật của bạn.",
    ]
    return SimulationNarrative(
        observation=observation, explanation=explanation, action=action, caveats=caveats
    )
