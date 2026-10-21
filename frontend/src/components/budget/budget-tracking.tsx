"use client";

import { RefreshCwIcon } from "lucide-react";
import { useState } from "react";

import {
  MonthProgressCard,
  MonthSummaryCards,
} from "@/components/budget/month-summary-cards";
import { BudgetVsActualTable } from "@/components/budget/budget-vs-actual-table";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  withQuery,
  type BudgetStatusReport,
  type BudgetZone,
  type BudgetZoneList,
  type ZoneRecalculateRequest,
} from "@/lib/api";

/** Tab "Theo dõi" của `/budget`: thẻ tổng + bảng Budget vs Actual + vùng linh hoạt (số liệu và
 * ngưỡng đều từ backend). */
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
  const zones = useApiData<BudgetZoneList>(
    withQuery(`/budgets/${budgetId}/zones`, { today }),
  );
  const [recalculating, setRecalculating] = useState(false);
  const [zoneError, setZoneError] = useState<string | null>(null);
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

  const zoneItems = zones.data?.items ?? [];
  const zoneById: Record<string, BudgetZone> = Object.fromEntries(
    zoneItems.map((z) => [z.allocation_id, z]),
  );
  const editable = data.status !== "closed";
  const uncalculated = zoneItems.filter(
    (z) => z.zone_mode === "auto" && !z.calculated,
  ).length;
  const stale = zoneItems.filter((z) => z.auto?.stale).length;

  function reload() {
    status.reload();
    zones.reload();
  }

  async function recalculate() {
    setRecalculating(true);
    setZoneError(null);
    try {
      const body: ZoneRecalculateRequest = { allocation_ids: null };
      await apiRequest<BudgetZoneList>(
        "POST",
        withQuery(`/budgets/${budgetId}/zones/recalculate`, { today }),
        body,
      );
      reload();
    } catch (err) {
      setZoneError(describeError(err));
    } finally {
      setRecalculating(false);
    }
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
            Bấm vào một dòng để xem các giao dịch tạo nên số thực tế. Cột “Vùng”
            cho biết khoản nào thật sự cần chú ý: 🟢 trong vùng thoải mái · 🟡
            đã vượt vùng thoải mái · 🔴 vượt ngưỡng cảnh báo.
            {data.status === "draft" &&
              " Ngân sách đang là nháp — kích hoạt ở tab “Kế hoạch” để trang chủ theo dõi."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 px-0">
          {(uncalculated > 0 || stale > 0 || zoneError) && (
            <div className="mx-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed px-3 py-2 text-sm">
              <span className="text-muted-foreground">
                {uncalculated > 0 &&
                  `${uncalculated} dòng chưa có vùng linh hoạt. `}
                {stale > 0 &&
                  `${stale} dòng có ngưỡng tự động cũ hơn dữ liệu hiện tại. `}
                {editable
                  ? "Vùng tự động tính từ 3–6 tháng gần nhất, không tính khoản bất thường."
                  : "Ngân sách đã đóng — mở lại để tính vùng."}
              </span>
              {editable && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={recalculate}
                  disabled={recalculating}
                >
                  <RefreshCwIcon />
                  {recalculating ? "Đang tính…" : "Tính vùng tự động"}
                </Button>
              )}
              {zoneError && (
                <p role="alert" className="w-full text-destructive">
                  {zoneError}
                </p>
              )}
            </div>
          )}
          {zones.error && !zones.data && (
            <p role="alert" className="mx-4 text-sm text-destructive">
              Không tải được vùng linh hoạt: {describeError(zones.error)}
            </p>
          )}
          <TooltipProvider>
            <BudgetVsActualTable
              status={data}
              zones={zoneById}
              zonesEditable={editable}
              onZoneChanged={reload}
            />
          </TooltipProvider>
        </CardContent>
      </Card>
    </div>
  );
}
