"""LangGraph Financial Coach (Phase 10, ADR-006).

    START → scope_check ─(ngoài phạm vi / yêu cầu ghi)→ END (template, không gọi model)
                 ↓
               agent ⇄ tools (ToolNode, tối đa MAX_TOOL_ROUNDS vòng / câu hỏi)
                 ↓ (trả lời cuối)
           response_guard ─(fail, còn lượt)→ agent (viết lại tối đa MAX_GUARD_RETRIES lần)
                 ↓ pass / hết lượt (→ câu trả lời dự phòng từ evidence)
                END

- `agent` gọi OpenAI function calling qua `ai/openai_client.chat_with_tools` (model smart). Hết
  `MAX_TOOL_ROUNDS` vòng tool → gọi lần cuối với `tool_choice="none"` để buộc trả lời.
- `tools` = `ToolNode` của 5 tool read-only (`agents/tools/finance_tools`) — chỉ gọi services.
- `response_guard` deterministic (`services/coach_guard`): số ⊆ output tool, giọng văn, cấu trúc.
- AI lỗi (`AIUnavailable`) không được bắt ở đây: user message đã lưu, router trả 503.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolInvocationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.tools import finance_tools
from app.agents.tools.registry import CoachToolContext, CoachToolRegistry
from app.ai import coach_prompt, openai_client
from app.ai.openai_client import ToolChatResult
from app.core.ai_usage import UsageTotals, log_usage
from app.core.errors import DomainError
from app.schemas.coach import ChatMessageMetadata, ChatTurn, CoachAnswer, ToolTraceItem
from app.services import coach_evidence, coach_guard

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_GUARD_RETRIES = 1
RECURSION_LIMIT = 40

# (messages OpenAI, schema tools, tool_choice) → kết quả model.
LLM = Callable[[list[dict[str, Any]], list[dict[str, Any]], str], ToolChatResult]


class CoachState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    turn_start: int
    guard_attempts: int
    guard_status: str
    problems: list[str]
    first_problems: list[str]
    answer: str
    done: bool


def default_llm(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]], tool_choice: str
) -> ToolChatResult:
    return openai_client.chat_with_tools(
        messages,
        tools,
        task=coach_prompt.TASK,
        model=openai_client.model_smart(),
        timeout=coach_prompt.TIMEOUT_SECONDS,
        tool_choice=tool_choice,
    )


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def to_openai_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            out.append({"role": "system", "content": _text(m.content)})
        elif isinstance(m, HumanMessage):
            out.append({"role": "user", "content": _text(m.content)})
        elif isinstance(m, AIMessage):
            item: dict[str, Any] = {"role": "assistant", "content": _text(m.content) or None}
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c["args"], ensure_ascii=False),
                        },
                    }
                    for c in m.tool_calls
                ]
            out.append(item)
        elif isinstance(m, ToolMessage):
            out.append(
                {"role": "tool", "tool_call_id": m.tool_call_id, "content": _text(m.content)}
            )
    return out


def _parse_args(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _tool_error(exc: Exception) -> str:
    """Lỗi nghiệp vụ / tham số → trả cho model tự sửa; lỗi khác (DB…) → raise."""
    if isinstance(exc, ToolInvocationError):
        return exc.message
    if isinstance(exc, DomainError):
        return f"Lỗi: {exc.detail}"
    if isinstance(exc, ValidationError | ValueError):
        return f"Tham số không hợp lệ: {exc}"
    raise exc


def _tool_rounds(state: CoachState) -> int:
    turn = state["messages"][state.get("turn_start", 0) :]
    return sum(1 for m in turn if isinstance(m, AIMessage) and m.tool_calls)


def build_coach_graph(
    ctx: CoachToolContext,
    usage: UsageTotals,
    *,
    llm: LLM | None = None,
    registry: CoachToolRegistry | None = None,
):
    call_llm = llm or default_llm
    tools = (registry or finance_tools.default_registry()).build(ctx)
    tool_schemas = [convert_to_openai_tool(t) for t in tools]
    recorder = ctx.recorder

    def record_tool_call(request, execute):
        call = request.tool_call
        with recorder.lock:
            recorder.begin(call["id"], call["name"], call.get("args") or {})
            started = time.perf_counter()
            error: str | None = None
            try:
                result = execute(request)
                if isinstance(result, ToolMessage) and result.status == "error":
                    error = _text(result.content)
                return result
            finally:
                recorder.finish(call["id"], int((time.perf_counter() - started) * 1000), error)

    tool_node = ToolNode(tools, handle_tool_errors=_tool_error, wrap_tool_call=record_tool_call)

    def scope_check(state: CoachState) -> CoachState:
        kind = coach_guard.classify_request(state["question"])
        if kind is None:
            return {}
        return {
            "answer": coach_guard.refusal_answer(kind, state["question"]),
            "guard_status": kind,
            "problems": [],
            "done": True,
        }

    def agent(state: CoachState) -> CoachState:
        force_final = _tool_rounds(state) >= MAX_TOOL_ROUNDS
        result = call_llm(
            to_openai_messages(state["messages"]),
            tool_schemas,
            "none" if force_final or not tool_schemas else "auto",
        )
        usage.add(result.model, result.prompt_tokens, result.completion_tokens, result.latency_ms)
        tool_calls = (
            []
            if force_final
            else [
                {"id": c.id, "name": c.name, "args": _parse_args(c.arguments), "type": "tool_call"}
                for c in result.tool_calls
            ]
        )
        return {"messages": [AIMessage(content=result.content or "", tool_calls=tool_calls)]}

    def response_guard(state: CoachState) -> CoachState:
        answer = _text(state["messages"][-1].content).strip()
        records = recorder.ordered()
        payloads = [r.output.model_dump(mode="json") for r in records if r.output is not None]
        allowed = coach_guard.allowed_numbers(payloads, state["question"], ctx.today)
        problems = coach_guard.check_answer(answer, allowed)
        attempts = state.get("guard_attempts", 0)
        if not problems:
            return {
                "answer": answer,
                "guard_status": "rewritten" if attempts else "passed",
                "done": True,
            }
        logger.warning("coach_guard attempt=%d problems=%s", attempts + 1, problems)
        first = state.get("first_problems") or problems
        if attempts < MAX_GUARD_RETRIES:
            return {
                "guard_attempts": attempts + 1,
                "first_problems": first,
                "messages": [HumanMessage(coach_prompt.rewrite_request(problems))],
            }
        calls = [(r.name, r.output) for r in records]
        return {
            "answer": coach_guard.fallback_answer(coach_evidence.all_evidence(calls)),
            "guard_status": "fallback",
            "first_problems": first,
            "problems": problems,
            "done": True,
        }

    def after_scope(state: CoachState) -> str:
        return END if state.get("done") else "agent"

    def after_agent(state: CoachState) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "response_guard"

    def after_guard(state: CoachState) -> str:
        return END if state.get("done") else "agent"

    graph = StateGraph(CoachState)
    graph.add_node("scope_check", scope_check)
    graph.add_node("agent", agent)
    graph.add_node("tools", tool_node)
    graph.add_node("response_guard", response_guard)
    graph.add_edge(START, "scope_check")
    graph.add_conditional_edges("scope_check", after_scope, ["agent", END])
    graph.add_conditional_edges("agent", after_agent, ["tools", "response_guard"])
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("response_guard", after_guard, ["agent", END])
    return graph.compile()


def _history_messages(history: list[ChatTurn]) -> list[BaseMessage]:
    return [
        HumanMessage(t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in history
    ]


def run_coach(
    db: Session,
    question: str,
    *,
    today: date,
    history: list[ChatTurn] | None = None,
    llm: LLM | None = None,
    registry: CoachToolRegistry | None = None,
) -> CoachAnswer:
    """Một lượt hỏi–đáp (không lưu DB). Raise `AIUnavailable` nếu model lỗi."""
    started = time.perf_counter()
    ctx = CoachToolContext(db=db, today=today)
    usage = UsageTotals()
    graph = build_coach_graph(ctx, usage, llm=llm, registry=registry)
    messages: list[BaseMessage] = [
        SystemMessage(coach_prompt.build_system_prompt(today)),
        *_history_messages(history or []),
        HumanMessage(question),
    ]
    state: CoachState = graph.invoke(  # type: ignore[assignment]
        {"messages": messages, "question": question, "turn_start": len(messages)},
        {"recursion_limit": RECURSION_LIMIT},
    )

    records = ctx.recorder.ordered()
    calls = [(r.name, r.output) for r in records]
    answer = state["answer"]
    evidence, refs = coach_evidence.select_evidence(calls, answer)
    trace = []
    for record, call_refs in zip(records, refs, strict=True):
        summary, count = (
            coach_evidence.summarize_result(record.output)
            if record.output is not None
            else (record.error or "Lỗi", 0)
        )
        trace.append(
            ToolTraceItem(
                name=record.name,
                args=record.args,
                result_summary=summary,
                result_count=count,
                evidence_refs=call_refs,
                latency_ms=record.latency_ms,
                error=record.error,
            )
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    tool_rounds = _tool_rounds(state)
    metadata = ChatMessageMetadata(
        model=usage.model,
        prompt_version=coach_prompt.PROMPT_VERSION if usage.calls else None,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated_cost_vnd=usage.estimated_cost_vnd,
        llm_calls=usage.calls,
        tool_rounds=tool_rounds,
        latency_ms=latency_ms,
        guard_status=state["guard_status"],  # type: ignore[typeddict-item]
        guard_problems=state.get("first_problems") or [],
    )
    log_usage(
        "coach",
        usage,
        latency_ms,
        tool_rounds=tool_rounds,
        tools=",".join(r.name for r in records) or "-",
        guard=metadata.guard_status,
    )
    return CoachAnswer(content=answer, tool_trace=trace, evidence=evidence, metadata=metadata)
