"""Prompt Financial Coach (`prompts/coach_v3.md`) + thông điệp yêu cầu viết lại khi guard fail."""

from datetime import date
from functools import cache
from pathlib import Path

from app.services.money import add_months

PROMPT_FILE = Path(__file__).parent / "prompts" / "coach_v3.md"
PROMPT_VERSION = "coach_v3"
TASK = "coach"
TIMEOUT_SECONDS = 60.0
_WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


@cache
def _template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def build_system_prompt(today: date) -> str:
    previous = add_months(today.replace(day=1), -1)
    return (
        _template()
        .replace("{{today}}", today.isoformat())
        .replace("{{weekday}}", _WEEKDAYS[today.weekday()])
        .replace("{{current_month}}", f"{today:%Y-%m}")
        .replace("{{previous_month}}", f"{previous:%Y-%m}")
    )


def rewrite_request(problems: list[str]) -> str:
    return (
        "Câu trả lời vừa rồi chưa đạt kiểm tra tự động: "
        + "; ".join(problems)
        + ". Hãy viết lại toàn bộ câu trả lời: chỉ dùng số copy nguyên từ kết quả tool (gọi thêm "
        "tool nếu cần), giữ cấu trúc **Quan sát** → **Vì sao** → **Bạn có thể cân nhắc** với gợi "
        "ý có điều kiện, giọng trung lập, không nhắc tên kỹ thuật."
    )
