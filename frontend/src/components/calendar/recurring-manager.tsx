"use client";

import { PauseIcon, PencilIcon, PlayIcon, PlusIcon, RepeatIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  apiRequest,
  describeError,
  withQuery,
  type RecurringTransaction,
  type RecurringUpdate,
} from "@/lib/api";
import { DUE_STATUS_LABELS, describeSchedule } from "@/lib/calendar";
import { formatDate, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Danh sách khoản định kỳ: sửa, tạm dừng / bật lại. */
export function RecurringManager({
  items,
  today,
  onAdd,
  onEdit,
  onChanged,
}: {
  items: RecurringTransaction[] | undefined;
  today: string;
  onAdd: () => void;
  onEdit: (item: RecurringTransaction) => void;
  onChanged: () => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function setActive(item: RecurringTransaction, active: boolean) {
    setBusyId(item.id);
    setError(null);
    try {
      await apiRequest<RecurringTransaction>(
        "PATCH",
        withQuery(`/recurring-transactions/${item.id}`, { today }),
        { active } satisfies RecurringUpdate,
      );
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RepeatIcon className="size-4" aria-hidden />
          Khoản định kỳ
        </CardTitle>
        <CardDescription>
          Lương, tiền nhà, internet, subscription… dùng để vẽ lịch và dự báo số dư.
        </CardDescription>
        <CardAction>
          <Button size="sm" onClick={onAdd}>
            <PlusIcon data-icon="inline-start" />
            Thêm khoản định kỳ
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {!items ? (
          <p className="text-sm text-muted-foreground">Đang tải…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Chưa có khoản định kỳ. Thêm thủ công hoặc dùng “Phát hiện từ lịch sử”.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Khoản</TableHead>
                <TableHead>Kỳ tới</TableHead>
                <TableHead className="text-right">Số tiền</TableHead>
                <TableHead className="text-right">Thao tác</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={r.id} className={cn(!r.active && "opacity-60")}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span aria-hidden>{r.icon}</span>
                      <div className="min-w-0">
                        <p className="font-medium">{r.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {describeSchedule(r)} · {r.category.name}
                          {r.auto_detected ? " · tự phát hiện" : ""}
                          {r.transaction_count ? ` · ${r.transaction_count} giao dịch` : ""}
                        </p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col items-start gap-1 text-sm">
                      <span>{formatDate(r.next_due_on)}</span>
                      {r.active ? (
                        <Badge variant={r.due_status === "overdue" ? "destructive" : "outline"}>
                          {DUE_STATUS_LABELS[r.due_status]}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">Tạm dừng</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right tabular-nums",
                      r.direction === "income" && "text-emerald-600",
                    )}
                  >
                    {r.direction === "income" ? "+" : "−"}
                    {formatVND(r.amount)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Sửa ${r.name}`}
                        onClick={() => onEdit(r)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={r.active ? `Tạm dừng ${r.name}` : `Bật lại ${r.name}`}
                        disabled={busyId !== null}
                        onClick={() => setActive(r, !r.active)}
                      >
                        {r.active ? <PauseIcon /> : <PlayIcon />}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
