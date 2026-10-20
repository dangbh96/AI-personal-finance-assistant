"use client";

import { TriangleAlertIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
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
  BudgetJar,
  BudgetTotals,
  BudgetWarning,
  FiftyThirtyTwentyReference,
} from "@/lib/api";
import {
  GROUP_LABELS,
  allocationLabel,
  parseBudgetAmount,
  type AllocationRow,
} from "@/lib/budget";
import { formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

function jarCategories(row: AllocationRow, jars: BudgetJar[] | undefined) {
  if (!row.jar_name || !jars) return null;
  const jar = jars.find((j) => j.name === row.jar_name);
  if (!jar) return null;
  if (jar.categories.length === 0) {
    return row.group === "savings" ? null : "Không gắn danh mục chi";
  }
  return jar.categories.map((c) => c.name).join(", ");
}

/** Bảng phân bổ: sửa từng số tiền; tổng / chưa phân bổ lấy từ backend (`totals`). */
export function AllocationPreviewTable({
  rows,
  onAmountChange,
  totals,
  expectedIncome,
  jars,
  readOnly = false,
  stale = false,
}: {
  rows: AllocationRow[];
  onAmountChange?: (index: number, text: string) => void;
  totals: BudgetTotals | undefined;
  expectedIncome: number | null;
  jars?: BudgetJar[];
  readOnly?: boolean;
  stale?: boolean;
}) {
  const over = totals !== undefined && totals.unallocated < 0;

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Phân bổ</TableHead>
          <TableHead>Nhóm</TableHead>
          <TableHead className="w-56 text-right">Số tiền dự kiến</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => {
          const label = allocationLabel(row);
          const invalid = parseBudgetAmount(row.amountText) === null;
          const detail = jarCategories(row, jars);
          return (
            <TableRow key={`${row.category_id ?? row.jar_name}-${index}`}>
              <TableCell className="whitespace-normal">
                <div className="font-medium">{label}</div>
                {detail && (
                  <div className="text-xs text-muted-foreground">{detail}</div>
                )}
                {row.group === "savings" && (
                  <div className="text-xs text-muted-foreground">
                    Để dành, không tính là chi tiêu
                  </div>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {GROUP_LABELS[row.group]}
              </TableCell>
              <TableCell className="text-right">
                {readOnly ? (
                  <span className="tabular-nums">
                    {formatVND(parseBudgetAmount(row.amountText) ?? 0)}
                  </span>
                ) : (
                  <div className="flex flex-col items-end gap-1">
                    <Input
                      aria-label={`Số tiền cho ${label}`}
                      inputMode="numeric"
                      className="w-40 text-right tabular-nums"
                      value={row.amountText}
                      aria-invalid={invalid}
                      onChange={(e) => onAmountChange?.(index, e.target.value)}
                    />
                    {invalid && (
                      <span className="text-xs text-destructive">
                        Số tiền không hợp lệ
                      </span>
                    )}
                  </div>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
      <TableFooter className={cn(stale && "opacity-60")}>
        <TableRow>
          <TableCell colSpan={2}>Tổng phân bổ</TableCell>
          <TableCell className="text-right tabular-nums">
            {totals ? formatVND(totals.planned_total) : "—"}
          </TableCell>
        </TableRow>
        <TableRow>
          <TableCell colSpan={2} className="font-normal text-muted-foreground">
            Thu nhập dự kiến
          </TableCell>
          <TableCell className="text-right font-normal tabular-nums text-muted-foreground">
            {expectedIncome === null ? "—" : formatVND(expectedIncome)}
          </TableCell>
        </TableRow>
        <TableRow>
          <TableCell colSpan={2} className={cn(over && "text-rose-600")}>
            {over ? "Vượt thu nhập dự kiến" : "Chưa phân bổ"}
          </TableCell>
          <TableCell
            className={cn("text-right tabular-nums", over && "text-rose-600")}
          >
            {totals ? formatVND(Math.abs(totals.unallocated)) : "—"}
          </TableCell>
        </TableRow>
      </TableFooter>
    </Table>
  );
}

export function BudgetWarnings({ warnings }: { warnings: BudgetWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2">
      {warnings.map((w) => (
        <li
          key={w.code}
          className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          {w.message}
        </li>
      ))}
    </ul>
  );
}

/** So sánh với mốc 50/30/20 — chỉ để tham khảo. */
export function ReferenceComparison({
  reference,
}: {
  reference: FiftyThirtyTwentyReference | undefined;
}) {
  if (!reference) return null;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted-foreground">
        Mốc 50/30/20 chỉ để bạn tham khảo, không phải luật. Nhóm “Bất thường”
        được tính chung vào “Mong muốn” khi so sánh.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nhóm</TableHead>
            <TableHead className="text-right">Ngân sách của bạn</TableHead>
            <TableHead className="text-right">Tham khảo 50/30/20</TableHead>
            <TableHead className="text-right">Chênh lệch</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reference.comparison.map((c) => (
            <TableRow key={c.group}>
              <TableCell>{GROUP_LABELS[c.group]}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatVND(c.planned)}
              </TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground">
                {formatVND(c.reference)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {c.difference === 0
                  ? "—"
                  : `${c.difference > 0 ? "+" : "−"}${formatVND(Math.abs(c.difference))}`}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
