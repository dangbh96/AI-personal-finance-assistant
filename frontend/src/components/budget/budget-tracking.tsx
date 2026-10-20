"use client";

import {
  MonthProgressCard,
  MonthSummaryCards,
} from "@/components/budget/month-summary-cards";
import { BudgetVsActualTable } from "@/components/budget/budget-vs-actual-table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, withQuery, type BudgetStatusReport } from "@/lib/api";

/** Tab "Theo dõi" của `/budget`: thẻ tổng + bảng Budget vs Actual (số liệu từ backend). */
export function BudgetTracking({
  budgetId,
  today,
}: {
  budgetId: string;
  today: string;
}) {
  const status = useApiData<BudgetStatusReport>(
    withQuery(`/budgets/${budgetId}/status`, { today }),
  );
  const data = status.data;

  if (status.error && !data) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {describeError(status.error)}
      </p>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <MonthSummaryCards
        incomeActual={data.totals.income_actual}
        expenseActual={data.totals.expense_actual}
        netActual={data.totals.net_actual}
        totals={data.totals}
      >
        <MonthProgressCard progress={data.progress} />
      </MonthSummaryCards>
      <Card className="pb-0">
        <CardHeader>
          <CardTitle>Ngân sách so với thực tế</CardTitle>
          <CardDescription>
            Bấm vào một dòng để xem các giao dịch tạo nên số thực tế.
            {data.status === "draft" &&
              " Ngân sách đang là nháp — kích hoạt ở tab “Kế hoạch” để trang chủ theo dõi."}
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0">
          <BudgetVsActualTable status={data} />
        </CardContent>
      </Card>
    </div>
  );
}
