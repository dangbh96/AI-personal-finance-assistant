import Link from "next/link";

import { TrackingStatusBadge } from "@/components/budget/budget-vs-actual-table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { MonthlyBudgetSummary } from "@/lib/api";
import { formatPercent, formatSignedVND, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Planned vs actual cả tháng (rút gọn từ Budget vs Actual — Phase 5). */
export function BudgetActualMiniTable({
  budget,
  month,
}: {
  budget: MonthlyBudgetSummary | null | undefined;
  /** "YYYY-MM" */
  month: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ngân sách so với thực tế</CardTitle>
        <CardDescription>
          {budget ? (
            <>
              Chi theo kế hoạch {formatVND(budget.expense_planned)} · thực chi{" "}
              {formatVND(budget.expense_actual)}.{" "}
              <Link
                href={`/budget?month=${month}&tab=track`}
                className="underline underline-offset-3"
              >
                Xem chi tiết
              </Link>
            </>
          ) : (
            "Tháng này chưa có ngân sách đang theo dõi."
          )}
        </CardDescription>
      </CardHeader>
      {budget ? (
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dòng</TableHead>
                <TableHead className="text-right">Kế hoạch</TableHead>
                <TableHead className="text-right">Thực tế</TableHead>
                <TableHead className="text-right">Chênh lệch</TableHead>
                <TableHead className="text-right">Đã dùng</TableHead>
                <TableHead>Trạng thái</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {budget.lines.map((line) => (
                <TableRow key={line.allocation_id}>
                  <TableCell>{line.label}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatVND(line.planned)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatVND(line.actual)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      line.variance > 0 && line.status === "over_budget" && "text-rose-600",
                    )}
                  >
                    {line.status === "not_tracked" ? "—" : formatSignedVND(line.variance)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {line.used_percent === null || line.used_percent === undefined
                      ? "—"
                      : formatPercent(line.used_percent)}
                  </TableCell>
                  <TableCell>
                    <TrackingStatusBadge status={line.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>Ngoài ngân sách</TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums">
                  {formatVND(budget.unbudgeted_actual)}
                </TableCell>
                <TableCell colSpan={3} />
              </TableRow>
            </TableFooter>
          </Table>
        </CardContent>
      ) : (
        <CardContent>
          <Link
            href={`/budget?month=${month}`}
            className="text-sm underline underline-offset-3"
          >
            Mở ngân sách tháng này
          </Link>
        </CardContent>
      )}
    </Card>
  );
}
