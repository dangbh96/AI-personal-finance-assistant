import type { ReactNode } from "react";

import { SpendingTypeBadge } from "@/components/spending-type-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AdviceTransaction, BudgetAdviceEvidence } from "@/lib/api";
import { formatDate, formatMonthLabel, formatPercent, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

function Row({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: ReactNode;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("tabular-nums", emphasis && "font-semibold")}>{value}</dd>
    </div>
  );
}

function TransactionLine({
  title,
  tx,
  share,
}: {
  title: string;
  tx: AdviceTransaction;
  share?: number | null;
}) {
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/60 p-3 text-sm dark:border-violet-900 dark:bg-violet-950/30">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{tx.note ?? tx.category_name}</span>
          <span className="text-xs text-muted-foreground">
            {tx.category_name} · {formatDate(tx.occurred_on)}
          </span>
          {tx.spending_type && <SpendingTypeBadge value={tx.spending_type} />}
        </span>
        <span className="font-semibold tabular-nums">{formatVND(tx.amount)}</span>
      </div>
      {share !== null && share !== undefined && (
        <p className="mt-1 text-xs text-muted-foreground">
          {share >= 100
            ? "Lớn hơn hoặc bằng toàn bộ phần vượt"
            : `Chiếm ${formatPercent(share)} phần vượt`}
        </p>
      )}
    </div>
  );
}

/** Số liệu làm căn cứ cho verdict — tất cả do backend tính (`advisor_rules`). */
export function EvidenceTable({ evidence: e }: { evidence: BudgetAdviceEvidence }) {
  const oneOffShare =
    e.rule === "one_off_irregular" ? e.irregular_share_pct : e.single_transaction_share_pct;
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid gap-1.5 sm:grid-cols-2 sm:gap-x-8">
        <Row label="Kế hoạch" value={formatVND(e.planned_amount)} />
        <Row label="Thực chi" value={formatVND(e.actual_amount)} emphasis />
        {e.comfort_high_used && e.comfort_high != null && (
          <Row label="Vùng an toàn (tới)" value={formatVND(e.comfort_high)} />
        )}
        <Row
          label={e.comfort_high_used ? "Vượt vùng an toàn" : "Vượt kế hoạch"}
          value={e.over_amount > 0 ? formatVND(e.over_amount) : "—"}
          emphasis={e.over_amount > 0}
        />
        <Row label="Số giao dịch" value={e.transaction_count} />
        {e.irregular_total > 0 && (
          <Row label="Trong đó bất thường" value={formatVND(e.irregular_total)} />
        )}
      </dl>
      {!e.month_complete && (
        <p className="text-xs text-muted-foreground">
          Tháng chưa kết thúc — số liệu tính đến {formatDate(e.as_of)}.
        </p>
      )}

      {e.one_off_transaction && (
        <TransactionLine
          title={
            e.rule === "one_off_irregular"
              ? "Khoản bất thường"
              : "Giao dịch đơn lẻ nổi trội"
          }
          tx={e.one_off_transaction}
          share={oneOffShare}
        />
      )}

      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">
          Thực chi {e.min_history_months} tháng gần nhất
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tháng</TableHead>
              <TableHead className="text-right">Thực chi</TableHead>
              <TableHead>So với kế hoạch {formatVND(e.planned_amount)}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {e.history_actuals.map((h) => (
              <TableRow key={h.month}>
                <TableCell>{formatMonthLabel(h.month.slice(0, 7))}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {h.has_data ? formatVND(h.actual) : "—"}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-xs",
                    h.over_planned ? "text-rose-600" : "text-muted-foreground",
                  )}
                >
                  {!h.has_data
                    ? "Chưa có dữ liệu"
                    : h.over_planned
                      ? "Vượt"
                      : "Trong kế hoạch"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <dl className="mt-2 grid gap-1.5 sm:grid-cols-2 sm:gap-x-8">
          <Row
            label="Số tháng có dữ liệu"
            value={`${e.history_months}/${e.min_history_months}`}
          />
          {e.history_median != null && (
            <Row label="Trung vị" value={formatVND(e.history_median)} />
          )}
          {e.cv_pct != null && (
            <Row
              label={`Độ dao động (CV, ổn định ≤ ${formatPercent(e.stable_cv_threshold_pct)})`}
              value={formatPercent(e.cv_pct)}
            />
          )}
        </dl>
      </div>

      {e.proposed_planned_amount != null && (
        <div className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-sky-200 bg-sky-50/60 p-3 text-sm dark:border-sky-900 dark:bg-sky-950/30">
          <span className="text-muted-foreground">
            Planned đề xuất (trung vị, làm tròn {formatVND(e.budget_rounding_step)})
          </span>
          <span className="font-semibold tabular-nums">
            {formatVND(e.proposed_planned_amount)}
          </span>
        </div>
      )}
    </div>
  );
}
