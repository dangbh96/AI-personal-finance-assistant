"""Registry tool read-only của Financial Coach (Phase 10).

Mỗi tool là một factory `(CoachToolContext) -> BaseTool` (tool cần `db` / `today` của request).
Các phase sau chỉ cần `register` thêm tool (`get_goals` P11, `search_transactions` P15,
`search_knowledge` P16, `simulate` P17); tên chưa đăng ký bị bỏ qua an toàn khi build.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.embedding_service import Embedder

logger = logging.getLogger(__name__)

# Thứ tự = thứ tự khai báo cho model.
COACH_TOOL_NAMES: tuple[str, ...] = (
    "get_spending_summary",
    "get_budget_status",
    "get_category_trend",
    "get_budget_advice",
    "get_recent_reviews",
    "get_goals",
    "search_transactions",
    "search_knowledge",
    "simulate",
)
FUTURE_TOOLS: dict[str, int] = {
    "get_goals": 11,
    "search_transactions": 15,
    "search_knowledge": 16,
    "simulate": 17,
}


@dataclass
class ToolRecord:
    """Kết quả một lần gọi tool (output Pydantic để dựng evidence + tập số được phép)."""

    call_id: str
    name: str
    args: dict[str, Any]
    output: BaseModel | None = None
    error: str | None = None
    latency_ms: int = 0


@dataclass
class ToolRecorder:
    """Ghi lại output từng lần gọi tool trong một lượt Coach.

    ToolNode có thể chạy nhiều tool song song bằng thread; mọi lần chạy được tuần tự hoá bằng
    `lock` (dùng chung 1 SQLAlchemy Session) nên `current` luôn là lần gọi đang chạy.
    """

    records: dict[str, ToolRecord] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    current: str | None = None

    def begin(self, call_id: str, name: str, args: dict[str, Any]) -> None:
        self.current = call_id
        self.records[call_id] = ToolRecord(call_id, name, dict(args))
        self.order.append(call_id)

    def store(self, output: BaseModel) -> str:
        """Lưu output của lần gọi hiện tại, trả JSON cho model."""
        if self.current is not None and self.current in self.records:
            self.records[self.current].output = output
        return output.model_dump_json()

    def finish(self, call_id: str, latency_ms: int, error: str | None) -> None:
        record = self.records[call_id]
        record.latency_ms = latency_ms
        if record.output is None:
            record.error = error or "Tool không trả kết quả"
        self.current = None

    def ordered(self) -> list[ToolRecord]:
        return [self.records[i] for i in self.order]


@dataclass
class CoachToolContext:
    db: Session
    today: date
    recorder: ToolRecorder = field(default_factory=ToolRecorder)
    # Embed câu tìm kiếm cho `search_transactions` (Phase 15); `coach_graph` gắn `ai/embeddings`.
    embedder: Embedder | None = None


ToolFactory = Callable[[CoachToolContext], BaseTool]


class CoachToolRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ToolFactory] = {}

    def register(self, name: str, factory: ToolFactory) -> None:
        self._factories[name] = factory

    def names(self) -> list[str]:
        return list(self._factories)

    def build(
        self, ctx: CoachToolContext, names: Iterable[str] = COACH_TOOL_NAMES
    ) -> list[BaseTool]:
        tools = []
        for name in names:
            factory = self._factories.get(name)
            if factory is None:
                logger.debug(
                    "coach tool %s chưa có (phase %s), bỏ qua", name, FUTURE_TOOLS.get(name)
                )
                continue
            tools.append(factory(ctx))
        return tools
