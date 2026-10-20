import type { ReactNode } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  AllocationStatus,
  BudgetStatusTotals,
  MonthProgress,
  TopContributor,
} from "@/lib/api";
import { allocationLabel } from "@/lib/budget";
import {
  formatDate,
  formatPercent,
  formatSignedVND,
  formatVND,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  valueClassName,
  children,
}: {
  label: string;
  value: ReactNode;
  valueClassName?: string;
  children?: ReactNode;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={cn("text-xl tabular-nums", valueClassName)}>
          {value}
        </CardTitle>
      </CardHeader>
      {children && (
        <CardContent className="flex flex-col gap-0.5 text-xs text-muted-foreground">
          {children}
        </CardContent>
      )}
    </Card>
  );
}

/** "900.000 ₫ từ 1 giao dịch" + dòng chi tiết (ghi chú · ngày · % phần vượt). */
export function TopContributorText({ top }: { top: TopContributor }) {
  return (
    <span className="flex flex-col">
      <span className="font-medium text-rose-700 dark:text-rose-300">
        {formatVND(top.amount)} từ 1 giao dịch
      </span>
      <span className="text-xs text-muted-foreground">
        {top.note ?? top.category.name} · {formatDate(top.occurred_on)} ·{" "}
        {formatPercent(top.share * 100)} phần vượt
      </span>
    </span>
  );
}

/** Thu nhập / chi tiêu / thu − chi của tháng; so với ngân sách nếu có `totals`. */
export function MonthSummaryCards({
  incomeActual,
  expenseActual,
  netActual,
  totals,
  children,
}: {
  incomeActual: number | undefined;
  expenseActual: number | undefined;
  netActual: number | undefined;
  totals?: BudgetStatusTotals | null;
  children?: ReactNode;
}) {
  const show = (value: number | undefined) =>
    value === undefined ? "—" : formatVND(value);
  return (
    <div
      className={cn(
        "grid gap-4 sm:grid-cols-2",
        children ? "lg:grid-cols-4" : "lg:grid-cols-3",
      )}
    >
      <StatCard
        label="Thu nhập thực tế"
        value={show(incomeActual)}
        valueClassName="text-emerald-600"
      >
        {totals && (
          <span>
            Dự kiến {formatVND(totals.income_expected)}
            {totals.income_variance !== 0 &&
              ` (${formatSignedVND(totals.income_variance)})`}
          </span>
        )}
      </StatCard>
      <StatCard
        label="Chi tiêu"
        value={show(expenseActual)}
        valueClassName="text-rose-600"
      >
        {totals && (
          <span>
            Kế hoạch {formatVND(totals.expense_planned)}
            {totals.expense_used_percent !== null &&
              totals.expense_used_percent !== undefined &&
              ` · đã dùng ${formatPercent(totals.expense_used_percent)}`}
          </span>
        )}
        {totals && totals.unbudgeted_actual > 0 && (
          <span>Ngoài ngân sách {formatVND(totals.unbudgeted_actual)}</span>
        )}
      </StatCard>
      <StatCard
        label="Thu − chi"
        value={show(netActual)}
        valueClassName={
          netActual !== undefined && netActual < 0 ? "text-rose-600" : undefined
        }
      >
        {totals && totals.savings_planned > 0 && (
          <span>Kế hoạch tiết kiệm {formatVND(totals.savings_planned)}</span>
        )}
      </StatCard>
      {children}
    </div>
  );
}

/** Thẻ "vượt nhiều nhất" (trang chủ). */
export function TopOverCard({ allocation }: { allocation: AllocationStatus | null }) {
  if (!allocation) {
    return (
      <StatCard
        label="Vượt ngân sách"
        value="Chưa có"
        valueClassName="text-emerald-600"
      >
        <span>Mọi khoản chi đang trong kế hoạch.</span>
      </StatCard>
    );
  }
  return (
    <StatCard
      label={`Vượt nhiều nhất · ${allocationLabel(allocation)}`}
      value={formatSignedVND(allocation.variance)}
      valueClassName="text-rose-600"
    >
      {allocation.top_contributor ? (
        <TopContributorText top={allocation.top_contributor} />
      ) : (
        <span>
          Thực tế {formatVND(allocation.actual)} / kế hoạch{" "}
          {formatVND(allocation.planned)}
        </span>
      )}
    </StatCard>
  );
}

/** Thẻ tiến độ tháng: ngày đã qua / số ngày. */
export function MonthProgressCard({ progress }: { progress: MonthProgress }) {
  return (
    <StatCard
      label="Tiến độ tháng"
      value={`Ngày ${progress.elapsed_days}/${progress.days_in_month}`}
    >
      <span>
        Đã qua {formatPercent(progress.month_progress * 100)} tháng. Cột
        “Nhịp” so % ngân sách đã dùng với mốc này.
      </span>
    </StatCard>
  );
}
