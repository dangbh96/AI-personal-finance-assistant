"use client";

import Link from "next/link";

import { AcceptAdviceDialog } from "@/components/budget-advice/accept-advice-dialog";
import { DismissButton } from "@/components/budget-advice/dismiss-button";
import { EvidenceTable } from "@/components/budget-advice/evidence-table";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AdviceVerdict, BudgetAdvice, BudgetAdviceAcceptResult } from "@/lib/api";
import { ADVICE_STATUS_LABELS, VERDICT_CLASSES, VERDICT_LABELS } from "@/lib/advice";
import { GROUP_LABELS } from "@/lib/budget";
import { formatMonthLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

export function VerdictBadge({ verdict }: { verdict: AdviceVerdict }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-4xl px-2 text-xs font-medium whitespace-nowrap",
        VERDICT_CLASSES[verdict],
      )}
    >
      {VERDICT_LABELS[verdict]}
    </span>
  );
}

function Narrative({ advice }: { advice: BudgetAdvice }) {
  const n = advice.narrative;
  if (!n) return <p className="text-sm">{advice.explanation}</p>;
  const source =
    n.generated_by === "ai"
      ? `Diễn giải bởi AI${advice.model ? ` (${advice.model})` : ""} từ số liệu bên dưới`
      : n.fallback_reason
        ? `Bản tự động — AI chưa dùng được (${n.fallback_reason})`
        : "Bản tự động";
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>{n.observation}</p>
      <p className="text-muted-foreground">{n.explanation}</p>
      {n.action && <p className="font-medium">{n.action}</p>}
      <p className="text-xs text-muted-foreground">{source}</p>
    </div>
  );
}

/** Một tư vấn: verdict (deterministic) + diễn giải + evidence + Accept / Dismiss. */
export function AdviceCard({
  advice,
  onChanged,
}: {
  advice: BudgetAdvice;
  onChanged: (message: string | null) => void;
}) {
  const canAccept =
    advice.status === "open" &&
    advice.verdict === "adjust_budget" &&
    advice.evidence.proposed_planned_amount != null;

  function accepted(result: BudgetAdviceAcceptResult) {
    const month = formatMonthLabel(result.budget.period_month.slice(0, 7)).toLowerCase();
    onChanged(
      result.budget.created
        ? `Đã tạo ngân sách nháp ${month} và áp dụng kế hoạch mới cho ${advice.allocation_label}.`
        : `Đã áp dụng kế hoạch mới cho ${advice.allocation_label} ${month}.`,
    );
  }

  return (
    <Card
      className={cn(advice.status !== "open" && "opacity-80")}
      data-verdict={advice.verdict}
    >
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {advice.category?.icon && <span aria-hidden>{advice.category.icon}</span>}
          {advice.allocation_label}
          <VerdictBadge verdict={advice.verdict} />
          {advice.status !== "open" && (
            <Badge variant="outline">{ADVICE_STATUS_LABELS[advice.status]}</Badge>
          )}
        </CardTitle>
        <CardDescription>
          Nhóm {GROUP_LABELS[advice.group].toLowerCase()} ·{" "}
          {formatMonthLabel(advice.month.slice(0, 7))}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Narrative advice={advice} />
        <EvidenceTable evidence={advice.evidence} />
        {advice.status === "accepted" && advice.applied_month && (
          <p className="text-sm">
            Đã áp dụng cho {formatMonthLabel(advice.applied_month.slice(0, 7)).toLowerCase()}.{" "}
            <Link
              href={`/budget?month=${advice.applied_month.slice(0, 7)}&tab=plan`}
              className="underline underline-offset-3"
            >
              Mở ngân sách tháng đó
            </Link>
          </p>
        )}
        {advice.status === "dismissed" && (
          <p className="text-sm text-muted-foreground">
            Đã bỏ qua{advice.dismiss_reason ? `: “${advice.dismiss_reason}”` : "."}
          </p>
        )}
      </CardContent>
      {advice.status === "open" && (
        <CardFooter className="flex flex-wrap gap-2">
          {canAccept && <AcceptAdviceDialog advice={advice} onAccepted={accepted} />}
          <DismissButton
            advice={advice}
            onDismissed={() => onChanged(`Đã bỏ qua tư vấn ${advice.allocation_label}.`)}
          />
        </CardFooter>
      )}
    </Card>
  );
}
