"use client";

import { PencilIcon, ReceiptTextIcon, SparklesIcon, Trash2Icon } from "lucide-react";

import { SpendingTypeBadge } from "@/components/spending-type-badge";
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
import type { Transaction } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import { SOURCE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function TransactionTable({
  items,
  onEdit,
  onDelete,
}: {
  items: Transaction[];
  onEdit: (tx: Transaction) => void;
  onDelete: (tx: Transaction) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Ngày</TableHead>
          <TableHead>Ghi chú</TableHead>
          <TableHead>Danh mục</TableHead>
          <TableHead>Loại chi tiêu</TableHead>
          <TableHead className="text-right">Số tiền</TableHead>
          <TableHead className="w-20" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((tx) => (
          <TableRow key={tx.id}>
            <TableCell className="tabular-nums">
              {formatDate(tx.occurred_on)}
            </TableCell>
            <TableCell
              className="max-w-40 truncate lg:max-w-64 xl:max-w-96"
              title={
                tx.raw_input ? `${tx.note ?? ""}\n“${tx.raw_input}”` : (tx.note ?? "")
              }
            >
              {tx.source !== "manual" && (
                <Badge variant="outline" className="mr-1.5">
                  {tx.source === "nl" && <SparklesIcon aria-hidden />}
                  {tx.source === "receipt" && <ReceiptTextIcon aria-hidden />}
                  {SOURCE_LABELS[tx.source]}
                </Badge>
              )}
              {tx.note ?? <span className="text-muted-foreground">—</span>}
            </TableCell>
            <TableCell>
              <span className="mr-1.5">{tx.category.icon}</span>
              {tx.category.name}
            </TableCell>
            <TableCell>
              {tx.spending_type ? (
                <SpendingTypeBadge value={tx.spending_type} />
              ) : (
                <span className="text-xs text-muted-foreground">Thu nhập</span>
              )}
            </TableCell>
            <TableCell
              className={cn(
                "text-right font-medium tabular-nums",
                tx.direction === "income" ? "text-emerald-600" : "text-rose-600",
              )}
            >
              {tx.direction === "income" ? "+" : "−"}
              {formatVND(tx.amount)}
            </TableCell>
            <TableCell className="text-right">
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Sửa giao dịch"
                onClick={() => onEdit(tx)}
              >
                <PencilIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Xoá giao dịch"
                onClick={() => onDelete(tx)}
              >
                <Trash2Icon />
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
