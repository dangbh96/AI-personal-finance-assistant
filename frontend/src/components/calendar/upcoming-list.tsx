"use client";

import { ClockIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  apiRequest,
  describeError,
  withQuery,
  type RecurringTransaction,
  type RecurringTransactionCreate,
  type RecurringTransactionResult,
} from "@/lib/api";
import { DUE_STATUS_LABELS, describeSchedule } from "@/lib/calendar";
import { formatDate, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

export const UPCOMING_DAYS = 14;

type Created = { name: string; result: RecurringTransactionResult };

/**
 * Khoản định kỳ đang bật đến hạn trong 14 ngày (kể cả quá hạn). "Tạo giao dịch" ghi kỳ này thành
 * giao dịch thật (`source = recurring`) và chuyển khoản sang kỳ sau.
 */
export function UpcomingList({
  items,
  today,
  onCreated,
}: {
  items: RecurringTransaction[] | undefined;
  today: string;
  onCreated: (result: RecurringTransactionResult) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);

  const upcoming = (items ?? []).filter(
    (r) => r.active && r.days_until_due <= UPCOMING_DAYS,
  );

  async function createTransaction(item: RecurringTransaction) {
    setBusyId(item.id);
    setError(null);
    setCreated(null);
    try {
      const result = await apiRequest<RecurringTransactionResult>(
        "POST",
        withQuery(`/recurring-transactions/${item.id}/create-transaction`, { today }),
        {} satisfies RecurringTransactionCreate,
      );
      setCreated({ name: item.name, result });
      onCreated(result);
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
          <ClockIcon className="size-4" aria-hidden />
          Sắp đến hạn ({UPCOMING_DAYS} ngày)
        </CardTitle>
        <CardDescription>
          Khi khoản đã thực sự thu / chi, bấm “Tạo giao dịch” để ghi lại. App không tự tạo giao
          dịch.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {created && (
          <p role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
            Đã ghi “{created.name}” {formatVND(created.result.transaction.amount)} ngày{" "}
            {formatDate(created.result.transaction.occurred_on)} · kỳ sau{" "}
            {formatDate(created.result.recurring.next_due_on)}.{" "}
            <Link href="/transactions" className="underline underline-offset-2">
              Xem ở Giao dịch
            </Link>
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {!items ? (
          <p className="text-sm text-muted-foreground">Đang tải…</p>
        ) : upcoming.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Không có khoản nào đến hạn trong {UPCOMING_DAYS} ngày tới.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {upcoming.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="text-xl" aria-hidden>
                    {r.icon}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{r.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(r.next_due_on)} · {describeSchedule(r)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant={r.due_status === "overdue" ? "destructive" : "outline"}
                  >
                    {DUE_STATUS_LABELS[r.due_status]}
                    {r.due_status === "upcoming" ? ` · ${r.days_until_due} ngày` : ""}
                  </Badge>
                  <span
                    className={cn(
                      "text-sm tabular-nums",
                      r.direction === "income" && "text-emerald-600",
                    )}
                  >
                    {r.direction === "income" ? "+" : "−"}
                    {formatVND(r.amount)}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId !== null}
                    onClick={() => createTransaction(r)}
                  >
                    {busyId === r.id ? "Đang ghi…" : "Tạo giao dịch"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
