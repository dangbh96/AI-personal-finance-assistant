"use client";

import Link from "next/link";
import { io } from "next/cache";
import { useRouter } from "next/navigation";
import { use } from "react";

import { BudgetEmptyState } from "@/components/budget/budget-empty-state";
import {
  MonthSummaryCards,
  TopOverCard,
} from "@/components/budget/month-summary-cards";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, withQuery, type MonthSummary } from "@/lib/api";
import { monthToPeriod } from "@/lib/budget";
import { currentMonth, todayISO } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";

/** Trang chủ: thu/chi/net tháng này, so với ngân sách nếu đã kích hoạt; CTA nếu chưa có. */
export function HomeMonthSummary() {
  use(io());
  const router = useRouter();
  const month = currentMonth();
  const summary = useApiData<MonthSummary>(
    withQuery("/dashboard/month-summary", {
      month: monthToPeriod(month),
      today: todayISO(),
    }),
  );
  const data = summary.data;
  const tracked = !!data?.budget;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-lg font-semibold">
          {formatMonthLabel(month)}
          {data && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ngày {data.progress.elapsed_days}/{data.progress.days_in_month}
            </span>
          )}
        </h2>
        {data?.budget_status && (
          <Link
            href={`/budget?month=${month}`}
            className="text-sm underline underline-offset-3"
          >
            Xem ngân sách
          </Link>
        )}
      </div>
      {summary.error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(summary.error)}
        </p>
      )}
      <MonthSummaryCards
        incomeActual={data?.income_actual}
        expenseActual={data?.expense_actual}
        netActual={data?.net_actual}
        totals={data?.budget}
      >
        {tracked && <TopOverCard allocation={data?.top_over ?? null} />}
      </MonthSummaryCards>
      {data && data.budget_status === null && (
        <BudgetEmptyState
          month={month}
          compact
          onCopied={() => router.push(`/budget?month=${month}&tab=plan`)}
        />
      )}
      {data?.budget_status === "draft" && (
        <p className="text-sm text-muted-foreground">
          Ngân sách tháng này đang là nháp.{" "}
          <Link
            href={`/budget?month=${month}&tab=plan`}
            className="text-foreground underline underline-offset-3"
          >
            Kích hoạt
          </Link>{" "}
          để so sánh chi tiêu thực tế với kế hoạch.
        </p>
      )}
    </section>
  );
}
