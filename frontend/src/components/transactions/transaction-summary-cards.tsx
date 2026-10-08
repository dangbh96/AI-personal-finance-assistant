import { SpendingTypeBadge } from "@/components/spending-type-badge";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { TransactionSummary } from "@/lib/api";
import { formatVND } from "@/lib/format";
import { SPENDING_TYPES } from "@/lib/labels";
import { cn } from "@/lib/utils";

function TotalCard({
  label,
  value,
  className,
}: {
  label: string;
  value: number | undefined;
  className?: string;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={cn("text-xl tabular-nums", className)}>
          {value === undefined ? "—" : formatVND(value)}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

export function TransactionSummaryCards({
  summary,
}: {
  summary: TransactionSummary | undefined;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-4 sm:grid-cols-3">
        <TotalCard
          label="Tổng thu"
          value={summary?.income_total}
          className="text-emerald-600"
        />
        <TotalCard
          label="Tổng chi"
          value={summary?.expense_total}
          className="text-rose-600"
        />
        <TotalCard
          label="Chênh lệch (thu − chi)"
          value={summary?.net}
          className={summary && summary.net < 0 ? "text-rose-600" : undefined}
        />
      </div>
      {summary && summary.expense_total > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span className="text-muted-foreground">Chi theo loại:</span>
          {SPENDING_TYPES.map((type) => (
            <span key={type} className="flex items-center gap-1.5">
              <SpendingTypeBadge value={type} />
              <span className="tabular-nums">
                {formatVND(summary.by_spending_type[type] ?? 0)}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
