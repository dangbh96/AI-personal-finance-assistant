"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { io } from "next/cache";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use } from "react";

import { BudgetEditor } from "@/components/budget/budget-editor";
import { BudgetEmptyState } from "@/components/budget/budget-empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApiData } from "@/hooks/use-api-data";
import {
  describeError,
  withQuery,
  type BudgetJarList,
  type BudgetList,
} from "@/lib/api";
import { monthToPeriod } from "@/lib/budget";
import { currentMonth, shiftMonth } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

/** `/budget`: ngân sách của tháng đang chọn (`?month=YYYY-MM`). Budget vs Actual ở Phase 5. */
export function BudgetView() {
  use(io());
  const router = useRouter();
  const pathname = usePathname();
  const param = useSearchParams().get("month");
  const month = param && MONTH_PATTERN.test(param) ? param : currentMonth();
  const period = monthToPeriod(month);

  const list = useApiData<BudgetList>(
    withQuery("/budgets", { from: period, to: period }),
  );
  const jars = useApiData<BudgetJarList>("/budgets/jars");
  const budget = list.data?.items[0];

  function goTo(next: string) {
    router.replace(`${pathname}?month=${next}`, { scroll: false });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Ngân sách</h1>
          <p className="text-sm text-muted-foreground">
            {formatMonthLabel(month)} · kế hoạch chi tiêu và tiết kiệm. So sánh
            với chi tiêu thực tế sẽ có ở Phase 5.
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng trước"
            onClick={() => goTo(shiftMonth(month, -1))}
          >
            <ChevronLeftIcon />
          </Button>
          <Input
            type="month"
            aria-label="Chọn tháng"
            className="w-40"
            value={month}
            onChange={(e) => e.target.value && goTo(e.target.value)}
          />
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng sau"
            onClick={() => goTo(shiftMonth(month, 1))}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </div>

      {list.error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(list.error)}
        </p>
      )}

      {list.loading && !list.data ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : budget ? (
        <BudgetEditor
          key={`${budget.id}-${budget.updated_at}`}
          budget={budget}
          jars={jars.data?.items}
          onChanged={list.reload}
          onDeleted={list.reload}
        />
      ) : (
        list.data && (
          <BudgetEmptyState month={month} onCopied={() => list.reload()} />
        )
      )}
    </div>
  );
}
