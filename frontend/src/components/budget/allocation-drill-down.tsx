"use client";

import { useState } from "react";

import { SpendingTypeBadge } from "@/components/spending-type-badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiData } from "@/hooks/use-api-data";
import {
  describeError,
  withQuery,
  type AllocationStatus,
  type TransactionList,
} from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import { SPENDING_TYPE_LABELS } from "@/lib/labels";

const PAGE_SIZE = 20;

function ScopeDescription({ allocation }: { allocation: AllocationStatus }) {
  const { scope } = allocation;
  if (scope.kind === "group") {
    return (
      <>
        Gồm các khoản chi loại{" "}
        {scope.spending_types.map((t) => SPENDING_TYPE_LABELS[t]).join(", ")}.
      </>
    );
  }
  if (scope.kind === "jar") {
    return (
      <>Gồm danh mục: {scope.categories.map((c) => c.name).join(", ")}.</>
    );
  }
  return null;
}

/** Giao dịch chi thuộc một dòng phân bổ trong tháng (backend lọc theo phạm vi của dòng). */
export function AllocationDrillDown({
  allocation,
}: {
  allocation: AllocationStatus;
}) {
  const [page, setPage] = useState(1);
  const list = useApiData<TransactionList>(
    withQuery(`/budget-allocations/${allocation.id}/transactions`, {
      page,
      page_size: PAGE_SIZE,
    }),
  );

  if (allocation.status === "not_tracked") {
    return (
      <p className="text-sm text-muted-foreground">
        Khoản tiết kiệm chưa được theo dõi bằng giao dịch — sẽ nối với mục tiêu
        tiết kiệm (Goals / Pay Yourself First) ở Phase 11.
      </p>
    );
  }

  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        <ScopeDescription allocation={allocation} />{" "}
        {data && `${data.total} giao dịch trong tháng.`}
      </p>
      {list.error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(list.error)}
        </p>
      )}
      {!data ? (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Chưa có giao dịch nào trong tháng.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ngày</TableHead>
              <TableHead>Ghi chú</TableHead>
              <TableHead>Danh mục</TableHead>
              <TableHead>Loại chi tiêu</TableHead>
              <TableHead className="text-right">Số tiền</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((tx) => (
              <TableRow
                key={tx.id}
                className={
                  tx.id === allocation.top_contributor?.transaction_id
                    ? "bg-rose-50 dark:bg-rose-950/40"
                    : undefined
                }
              >
                <TableCell className="tabular-nums">
                  {formatDate(tx.occurred_on)}
                </TableCell>
                <TableCell className="max-w-64 truncate">
                  {tx.note ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell>
                  <span className="mr-1.5">{tx.category.icon}</span>
                  {tx.category.name}
                </TableCell>
                <TableCell>
                  {tx.spending_type && (
                    <SpendingTypeBadge value={tx.spending_type} />
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(tx.amount)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || list.loading}
            onClick={() => setPage((p) => p - 1)}
          >
            Trước
          </Button>
          <span className="tabular-nums text-muted-foreground">
            Trang {page}/{pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages || list.loading}
            onClick={() => setPage((p) => p + 1)}
          >
            Sau
          </Button>
        </div>
      )}
    </div>
  );
}
