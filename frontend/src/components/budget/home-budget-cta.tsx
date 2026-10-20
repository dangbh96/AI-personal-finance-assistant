"use client";

import { io } from "next/cache";
import { useRouter } from "next/navigation";
import { use } from "react";

import { BudgetEmptyState } from "@/components/budget/budget-empty-state";
import { useApiData } from "@/hooks/use-api-data";
import { withQuery, type BudgetList } from "@/lib/api";
import { monthToPeriod } from "@/lib/budget";
import { currentMonth } from "@/lib/dates";

/** Trang chủ: nhắc tạo ngân sách nếu tháng hiện tại chưa có. */
export function HomeBudgetCta() {
  use(io());
  const router = useRouter();
  const month = currentMonth();
  const period = monthToPeriod(month);
  const list = useApiData<BudgetList>(
    withQuery("/budgets", { from: period, to: period }),
  );

  if (!list.data || list.data.items.length > 0) return null;
  return (
    <BudgetEmptyState
      month={month}
      compact
      onCopied={() => router.push(`/budget?month=${month}`)}
    />
  );
}
