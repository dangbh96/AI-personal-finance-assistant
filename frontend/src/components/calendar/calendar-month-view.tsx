"use client";

import { CalendarDaysIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

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
import type { CalendarEvent, CalendarMonth } from "@/lib/api";
import { EVENT_KIND_LABELS, WEEKDAY_SHORT, formatDayMonth, monthGrid } from "@/lib/calendar";
import { shiftMonth } from "@/lib/dates";
import { formatMonthLabel, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

function eventTitle(e: CalendarEvent): string {
  const sign = e.direction === "income" ? "+" : "−";
  const state = e.overdue ? " · quá hạn" : e.kind === "paid" ? " · đã ghi" : "";
  return `${e.icon} ${e.label}: ${sign}${formatVND(e.amount)}${state}`;
}

/**
 * Lịch tháng: mỗi ô là một ngày với icon các khoản tiền (💰 thu, 🏠 nhà, 💳 thẻ, 📱 tiện ích,
 * 🎯 để dành mục tiêu) + danh sách sự kiện của tháng bên dưới. Mọi số từ `GET /calendar/month`.
 */
export function CalendarMonthView({
  month,
  today,
  data,
  loading,
  onMonthChange,
}: {
  month: string;
  today: string;
  data: CalendarMonth | undefined;
  loading: boolean;
  onMonthChange: (month: string) => void;
}) {
  const events = data?.events ?? [];
  const byDay = new Map<string, CalendarEvent[]>();
  for (const e of events) {
    byDay.set(e.date, [...(byDay.get(e.date) ?? []), e]);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDaysIcon className="size-4" aria-hidden />
          {formatMonthLabel(month)}
        </CardTitle>
        <CardDescription>
          {data
            ? `Thu ${formatVND(data.income_total)} · chi ${formatVND(data.expense_total)} · để dành ${formatVND(data.goal_saving_total)}`
            : loading
              ? "Đang tải…"
              : ""}
        </CardDescription>
        <CardAction className="flex gap-1">
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng trước"
            onClick={() => onMonthChange(shiftMonth(month, -1))}
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng sau"
            onClick={() => onMonthChange(shiftMonth(month, 1))}
          >
            <ChevronRightIcon />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-7 gap-1 text-center text-xs">
          {WEEKDAY_SHORT.map((d) => (
            <div key={d} className="py-1 font-medium text-muted-foreground" aria-hidden>
              {d}
            </div>
          ))}
          {monthGrid(month).map((day, i) =>
            day === null ? (
              <div key={`empty-${i}`} aria-hidden />
            ) : (
              <div
                key={day}
                data-date={day}
                className={cn(
                  "flex min-h-16 flex-col items-start gap-0.5 rounded-md border p-1 text-left",
                  day === today && "border-primary ring-1 ring-primary",
                  day < today && "bg-muted/40",
                )}
              >
                <span className={cn("text-[11px] tabular-nums", day === today && "font-semibold")}>
                  {Number(day.slice(8))}
                </span>
                <div className="flex flex-wrap gap-0.5">
                  {(byDay.get(day) ?? []).map((e, j) => (
                    <span
                      key={j}
                      title={eventTitle(e)}
                      className={cn(
                        "text-base leading-none",
                        e.kind === "paid" && "opacity-50",
                        e.overdue && "rounded-sm ring-1 ring-rose-500",
                      )}
                    >
                      <span aria-hidden>{e.icon}</span>
                      <span className="sr-only">{`${formatDayMonth(day)} ${eventTitle(e)}`}</span>
                    </span>
                  ))}
                </div>
              </div>
            ),
          )}
        </div>

        {data && events.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Tháng này chưa có khoản định kỳ nào. Thêm lương, tiền nhà, internet… ở mục “Khoản định
            kỳ” bên dưới.
          </p>
        ) : (
          <ul className="flex flex-col divide-y text-sm" aria-label="Sự kiện trong tháng">
            {events.map((e, i) => (
              <li key={i} className="flex items-center justify-between gap-2 py-1.5">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="w-10 shrink-0 text-xs text-muted-foreground tabular-nums">
                    {formatDayMonth(e.date)}
                  </span>
                  <span aria-hidden>{e.icon}</span>
                  <span className="truncate">{e.label}</span>
                  <Badge variant={e.overdue ? "destructive" : e.kind === "paid" ? "secondary" : "outline"}>
                    {e.overdue ? "Quá hạn" : EVENT_KIND_LABELS[e.kind]}
                  </Badge>
                </span>
                <span
                  className={cn(
                    "shrink-0 tabular-nums",
                    e.direction === "income" ? "text-emerald-600" : "text-foreground",
                  )}
                >
                  {e.direction === "income" ? "+" : "−"}
                  {formatVND(e.amount)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
