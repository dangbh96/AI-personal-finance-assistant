"use client";

import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { io } from "next/cache";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use } from "react";

import { BudgetEditor } from "@/components/budget/budget-editor";
import { BudgetEmptyState } from "@/components/budget/budget-empty-state";
import { BudgetTracking } from "@/components/budget/budget-tracking";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApiData } from "@/hooks/use-api-data";
import {
  describeError,
  withQuery,
  type BudgetJarList,
  type BudgetList,
} from "@/lib/api";
import { monthToPeriod } from "@/lib/budget";
import { currentMonth, shiftMonth, todayISO } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
const DATE_PATTERN = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const TABS = ["track", "plan"] as const;
type Tab = (typeof TABS)[number];

/**
 * `/budget`: ngân sách của tháng đang chọn (`?month=YYYY-MM`). Tab "Theo dõi" (Budget vs
 * Actual) và "Kế hoạch" (sửa planned) lưu ở `?tab=`; `?today=YYYY-MM-DD` đổi ngày tính tiến độ
 * tháng (để thử pro-rata).
 */
export function BudgetView() {
  use(io());
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const monthParam = params.get("month");
  const month =
    monthParam && MONTH_PATTERN.test(monthParam) ? monthParam : currentMonth();
  const todayParam = params.get("today");
  const today =
    todayParam && DATE_PATTERN.test(todayParam) ? todayParam : todayISO();
  const period = monthToPeriod(month);

  const list = useApiData<BudgetList>(
    withQuery("/budgets", { from: period, to: period }),
  );
  const jars = useApiData<BudgetJarList>("/budgets/jars");
  const budget = list.data?.items[0];
  const tabParam = params.get("tab");
  const tab: Tab = TABS.includes(tabParam as Tab)
    ? (tabParam as Tab)
    : budget?.status === "draft"
      ? "plan"
      : "track";

  function navigate(changes: Record<string, string>) {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) next.set(key, value);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  function goTo(next: string) {
    navigate({ month: next });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Ngân sách</h1>
          <p className="text-sm text-muted-foreground">
            {formatMonthLabel(month)} · kế hoạch chi tiêu và tiết kiệm so với
            thực tế.
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
        <Tabs
          value={tab}
          onValueChange={(value) => navigate({ tab: String(value) })}
          className="gap-4"
        >
          <TabsList>
            <TabsTrigger value="track">Theo dõi</TabsTrigger>
            <TabsTrigger value="plan">Kế hoạch</TabsTrigger>
          </TabsList>
          <TabsContent value="track">
            <BudgetTracking
              key={`${budget.id}-${budget.updated_at}`}
              budgetId={budget.id}
              today={today}
            />
          </TabsContent>
          <TabsContent value="plan">
            <BudgetEditor
              key={`${budget.id}-${budget.updated_at}`}
              budget={budget}
              jars={jars.data?.items}
              onChanged={list.reload}
              onDeleted={list.reload}
            />
          </TabsContent>
        </Tabs>
      ) : (
        list.data && (
          <BudgetEmptyState month={month} onCopied={() => list.reload()} />
        )
      )}
    </div>
  );
}
