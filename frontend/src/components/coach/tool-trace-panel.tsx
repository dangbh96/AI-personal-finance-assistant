import { WrenchIcon } from "lucide-react";

import type { ToolTraceItem } from "@/lib/api";
import { TOOL_LABELS } from "@/lib/coach";

function formatArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args);
  if (entries.length === 0) return "(mặc định)";
  return entries.map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
}

/** Các tool Coach đã gọi: tên, tham số, số dòng kết quả, thời gian (không hiển thị prompt). */
export function ToolTracePanel({ items }: { items: ToolTraceItem[] }) {
  if (items.length === 0) return null;
  return (
    <details className="group rounded-lg border text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground select-none hover:text-foreground">
        <WrenchIcon className="size-3.5" />
        Tool trace ({items.length})
        <span className="ml-auto group-open:hidden">Xem</span>
        <span className="ml-auto hidden group-open:inline">Ẩn</span>
      </summary>
      <ol className="flex flex-col divide-y border-t">
        {items.map((t, i) => (
          <li key={i} className="flex flex-col gap-1 px-3 py-2">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <code className="font-mono text-xs font-semibold">{t.name}</code>
              {TOOL_LABELS[t.name] && (
                <span className="text-xs text-muted-foreground">{TOOL_LABELS[t.name]}</span>
              )}
              <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                {t.latency_ms} ms
              </span>
            </div>
            <code className="font-mono text-xs break-all text-muted-foreground">
              {formatArgs(t.args)}
            </code>
            {t.error ? (
              <p className="text-xs text-destructive">{t.error}</p>
            ) : (
              <p className="text-xs">
                {t.result_summary}
                {t.evidence_refs.length > 0 && (
                  <span className="text-muted-foreground"> · dùng {t.evidence_refs.join(", ")}</span>
                )}
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
