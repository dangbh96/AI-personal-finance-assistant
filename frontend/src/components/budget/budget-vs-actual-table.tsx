"use client";

import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import { Fragment, useState } from "react";

import { AllocationDrillDown } from "@/components/budget/allocation-drill-down";
import { TopContributorText } from "@/components/budget/month-summary-cards";
import { EarlyWarningLine, ZoneTooltip } from "@/components/budget/zone-badge";
import { ZoneSettingsDialog } from "@/components/budget/zone-settings-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  AllocationStatus,
  AllocationTrackingStatus,
  BudgetStatusReport,
  BudgetZone,
} from "@/lib/api";
import {
  GROUP_LABELS,
  PACE_LABELS,
  TRACKING_STATUS_CLASSES,
  TRACKING_STATUS_LABELS,
  allocationLabel,
} from "@/lib/budget";
import { formatPercent, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

const BAR_CLASSES: Record<AllocationTrackingStatus, string> = {
  on_track: "bg-emerald-500",
  ahead_of_pace: "bg-amber-500",
  over_budget: "bg-rose-500",
  not_tracked: "bg-muted-foreground/40",
};

export function TrackingStatusBadge({
  status,
}: {
  status: AllocationTrackingStatus;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-4xl px-2 text-xs font-medium whitespace-nowrap",
        TRACKING_STATUS_CLASSES[status],
      )}
    >
      {TRACKING_STATUS_LABELS[status]}
    </span>
  );
}

/** Thanh % đã dùng (tối đa 100%) + vạch % tháng đã qua. */
function UsedBar({
  allocation,
  monthProgress,
}: {
  allocation: AllocationStatus;
  monthProgress: number;
}) {
  const used = allocation.used_percent;
  return (
    <div className="flex flex-col items-end gap-1">
      <span className="tabular-nums">
        {used === null || used === undefined ? "—" : formatPercent(used)}
      </span>
      {used !== null && used !== undefined && (
        <div className="relative h-1.5 w-24 rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full",
              BAR_CLASSES[allocation.status],
            )}
            style={{ width: `${Math.min(used, 100)}%` }}
          />
          {allocation.status !== "not_tracked" && (
            <div
              className="absolute -top-0.5 h-2.5 w-px bg-foreground/60"
              style={{ left: `${monthProgress * 100}%` }}
              title="Mốc % tháng đã qua"
            />
          )}
        </div>
      )}
    </div>
  );
}

function RemainingCell({ allocation }: { allocation: AllocationStatus }) {
  if (allocation.status === "not_tracked") {
    return <span className="text-muted-foreground">—</span>;
  }
  if (allocation.variance > 0) {
    return (
      <span className="font-medium text-rose-600">
        Vượt {formatVND(allocation.variance)}
      </span>
    );
  }
  if (allocation.remaining === 0) {
    return <span>Dùng hết</span>;
  }
  return <span>Còn {formatVND(allocation.remaining)}</span>;
}

/** Bảng planned vs actual từng dòng; bấm một dòng để xem giao dịch của dòng đó. Cột "Vùng"
 * (Phase 9) lấy từ `GET /budgets/{id}/zones` — ngưỡng và trạng thái do backend tính. */
export function BudgetVsActualTable({
  status,
  zones,
  zonesEditable = false,
  onZoneChanged,
}: {
  status: BudgetStatusReport;
  zones?: Record<string, BudgetZone>;
  zonesEditable?: boolean;
  onZoneChanged?: () => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const { totals, progress } = status;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Phân bổ</TableHead>
          <TableHead className="text-right">Dự kiến</TableHead>
          <TableHead className="text-right">Thực tế</TableHead>
          <TableHead className="text-right">Còn lại / Vượt</TableHead>
          <TableHead className="text-right">Đã dùng</TableHead>
          <TableHead>Vùng</TableHead>
          <TableHead>Nhịp</TableHead>
          <TableHead>Giao dịch gây vượt</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {status.allocations.map((a) => {
          const open = openId === a.id;
          const zone = zones?.[a.id];
          return (
            <Fragment key={a.id}>
              <TableRow
                className="cursor-pointer"
                aria-expanded={open}
                onClick={() => setOpenId(open ? null : a.id)}
              >
                <TableCell className="whitespace-normal">
                  <div className="flex items-start gap-1.5">
                    {open ? (
                      <ChevronDownIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronRightIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    )}
                    <div className="flex flex-col gap-1">
                      <span className="font-medium">{allocationLabel(a)}</span>
                      <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {GROUP_LABELS[a.group]}
                        <TrackingStatusBadge status={a.status} />
                      </span>
                      {zone && <EarlyWarningLine zone={zone} />}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(a.planned)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {a.status === "not_tracked" ? "—" : formatVND(a.actual)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <RemainingCell allocation={a} />
                </TableCell>
                <TableCell className="text-right">
                  <UsedBar
                    allocation={a}
                    monthProgress={progress.month_progress}
                  />
                </TableCell>
                <TableCell>
                  {zone ? (
                    <div className="flex items-center gap-0.5">
                      <ZoneTooltip zone={zone} />
                      <ZoneSettingsDialog
                        zone={zone}
                        disabled={!zonesEditable}
                        onSaved={() => onZoneChanged?.()}
                      />
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell
                  className="text-sm"
                  title={
                    a.pace_status
                      ? `Theo nhịp tháng, tới hôm nay chi khoảng ${formatVND(a.expected_to_date)}`
                      : undefined
                  }
                >
                  {a.pace_status ? (
                    <span
                      className={cn(
                        a.pace_status === "ahead" &&
                          "text-amber-700 dark:text-amber-300",
                      )}
                    >
                      {PACE_LABELS[a.pace_status]}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-normal">
                  {a.top_contributor ? (
                    <TopContributorText top={a.top_contributor} />
                  ) : a.status === "not_tracked" ? (
                    <span className="text-xs text-muted-foreground">
                      Tiết kiệm sẽ nối với Goals/PYF ở Phase 11
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
              {open && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={8} className="bg-muted/30 whitespace-normal">
                    <AllocationDrillDown allocation={a} />
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          );
        })}
      </TableBody>
      <TableFooter>
        <TableRow>
          <TableCell>Tổng chi tiêu</TableCell>
          <TableCell className="text-right tabular-nums">
            {formatVND(totals.expense_planned)}
          </TableCell>
          <TableCell className="text-right tabular-nums">
            {formatVND(totals.expense_actual)}
          </TableCell>
          <TableCell className="text-right tabular-nums">
            {totals.expense_variance > 0 ? (
              <span className="text-rose-600">
                Vượt {formatVND(totals.expense_variance)}
              </span>
            ) : (
              <>Còn {formatVND(-totals.expense_variance)}</>
            )}
          </TableCell>
          <TableCell className="text-right tabular-nums">
            {totals.expense_used_percent === null ||
            totals.expense_used_percent === undefined
              ? "—"
              : formatPercent(totals.expense_used_percent)}
          </TableCell>
          <TableCell colSpan={3} />
        </TableRow>
        {totals.unbudgeted_actual > 0 && (
          <TableRow>
            <TableCell
              colSpan={2}
              className="font-normal text-muted-foreground"
            >
              Trong đó chi ngoài các dòng ngân sách
            </TableCell>
            <TableCell className="text-right font-normal tabular-nums text-muted-foreground">
              {formatVND(totals.unbudgeted_actual)}
            </TableCell>
            <TableCell colSpan={5} />
          </TableRow>
        )}
      </TableFooter>
    </Table>
  );
}
