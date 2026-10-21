import { BotIcon } from "lucide-react";

import { CoachAnswerText } from "@/components/coach/coach-answer-text";
import { EvidenceTable } from "@/components/coach/evidence-table";
import { ToolTracePanel } from "@/components/coach/tool-trace-panel";
import type { ChatMessage } from "@/lib/api";
import { GUARD_LABELS, GUARD_TONES } from "@/lib/coach";
import { formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

function MetaLine({ message }: { message: ChatMessage }) {
  const meta = message.metadata;
  if (!meta) return null;
  const parts = [
    meta.model,
    meta.total_tokens > 0 ? `${meta.total_tokens.toLocaleString("vi-VN")} token` : null,
    meta.estimated_cost_vnd !== null && meta.estimated_cost_vnd !== undefined
      ? `~${formatVND(meta.estimated_cost_vnd)}`
      : null,
    meta.llm_calls > 0
      ? `${(meta.latency_ms / 1000).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} giây`
      : "không gọi AI",
  ].filter(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span
        className={cn("rounded-4xl border px-2 py-0.5 font-medium", GUARD_TONES[meta.guard_status])}
      >
        {GUARD_LABELS[meta.guard_status]}
      </span>
      <span>{parts.join(" · ")}</span>
    </div>
  );
}

export function CoachMessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </p>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted">
        <BotIcon className="size-4" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-2xl rounded-tl-md border bg-card p-4">
        <CoachAnswerText content={message.content} />
        {message.evidence && <EvidenceTable items={message.evidence} />}
        {message.tool_calls && <ToolTracePanel items={message.tool_calls} />}
        <MetaLine message={message} />
      </div>
    </div>
  );
}
