"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ReceiptListItem, ReceiptStatus } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import { RECEIPT_STATUS_CLASSES, RECEIPT_STATUS_LABELS } from "@/lib/receipts";

const STATUS_FILTERS: { value: ReceiptStatus | "all"; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "extracted", label: "Chờ xác nhận" },
  { value: "confirmed", label: "Đã lưu" },
  { value: "failed", label: "Chưa đọc được" },
];

function uploadedAt(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Lịch sử hoá đơn đã upload (mới nhất trước): trạng thái, link giao dịch nếu đã lưu. */
export function ReceiptHistoryTable({
  items,
  loading,
  statusFilter,
  onStatusFilterChange,
  onOpen,
  activeId,
}: {
  items: ReceiptListItem[] | undefined;
  loading: boolean;
  statusFilter: ReceiptStatus | "all";
  onStatusFilterChange: (status: ReceiptStatus | "all") => void;
  onOpen: (receiptId: string) => void;
  activeId: string | null;
}) {
  return (
    <section aria-label="Lịch sử hoá đơn" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-heading text-lg font-semibold">Hoá đơn đã tải lên</h2>
        <div role="radiogroup" aria-label="Lọc theo trạng thái" className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.value}
              size="sm"
              role="radio"
              aria-checked={statusFilter === f.value}
              variant={statusFilter === f.value ? "secondary" : "ghost"}
              onClick={() => onStatusFilterChange(f.value)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {!items || items.length === 0 ? (
        <p className="rounded-lg border p-6 text-center text-sm text-muted-foreground">
          {loading && !items ? "Đang tải…" : "Chưa có hoá đơn nào."}
        </p>
      ) : (
        <div className={loading ? "rounded-lg border opacity-60" : "rounded-lg border"}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tải lên</TableHead>
                <TableHead>Cửa hàng</TableHead>
                <TableHead>Ngày HĐ</TableHead>
                <TableHead className="text-right">Tổng</TableHead>
                <TableHead>Trạng thái</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Thao tác</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow
                  key={item.id}
                  data-state={item.id === activeId ? "selected" : undefined}
                >
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {uploadedAt(item.created_at)}
                  </TableCell>
                  <TableCell className="max-w-56">
                    <p className="truncate">{item.merchant ?? "—"}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {item.original_filename}
                    </p>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    {item.receipt_date ? formatDate(item.receipt_date) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.total !== null && item.total !== undefined
                      ? formatVND(item.total)
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={RECEIPT_STATUS_CLASSES[item.status]}>
                      {RECEIPT_STATUS_LABELS[item.status]}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {item.transaction_id && item.transaction_occurred_on && (
                      <Link
                        href={`/transactions?month=${item.transaction_occurred_on.slice(0, 7)}`}
                        className="mr-2 text-sm text-primary underline-offset-4 hover:underline"
                      >
                        Giao dịch
                      </Link>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => onOpen(item.id)}>
                      Xem
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}
