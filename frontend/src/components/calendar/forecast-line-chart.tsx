"use client";

import { AlertTriangleIcon, TrendingUpIcon } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ForecastOutput, ForecastPoint } from "@/lib/api";
import { formatDayMonth } from "@/lib/calendar";
import { formatDate, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

const compact = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });
const LINE_COLOR = "#0ea5e9";
const WARNING_COLOR = "#e11d48";
export const FORECAST_DAY_OPTIONS = [30, 60] as const;
export type ForecastDays = (typeof FORECAST_DAY_OPTIONS)[number];

function ForecastTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: readonly { payload?: ForecastPoint }[];
}) {
  const point = active ? payload?.[0]?.payload : undefined;
  if (!point) return null;
  return (
    <div className="rounded-md border bg-background p-2 text-xs shadow-sm">
      <p className="font-medium">{formatDate(point.date)}</p>
      <p className="tabular-nums">Số dư dự báo: {formatVND(point.projected_balance)}</p>
      {point.events.map((e, i) => (
        <p key={i} className="text-muted-foreground">
          {e.icon} {e.label}: {e.direction === "income" ? "+" : "−"}
          {formatVND(e.amount)}
        </p>
      ))}
    </div>
  );
}

/** Đường số dư dự báo 30 / 60 ngày + ngưỡng cảnh báo + ngày đầu tiên dưới ngưỡng. */
export function ForecastLineChart({
  forecast,
  days,
  onDaysChange,
  loading,
}: {
  forecast: ForecastOutput | undefined;
  days: ForecastDays;
  onDaysChange: (days: ForecastDays) => void;
  loading: boolean;
}) {
  const warning = forecast?.low_balance_warning_day ?? null;
  const warningPoint = forecast?.points.find((p) => p.date === warning);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUpIcon className="size-4" aria-hidden />
          Dự báo số dư {days} ngày
        </CardTitle>
        <CardDescription>
          Số dư hiện có + khoản định kỳ + để dành mục tiêu − chi tiêu biến đổi trung bình mỗi
          ngày.
        </CardDescription>
        <CardAction>
          <div
            role="radiogroup"
            aria-label="Số ngày dự báo"
            className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1"
          >
            {FORECAST_DAY_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={days === option}
                onClick={() => onDaysChange(option)}
                className={cn(
                  "h-7 rounded-md px-3 text-sm font-medium transition-colors",
                  days === option
                    ? "bg-background shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option} ngày
              </button>
            ))}
          </div>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!forecast ? (
          <p className="text-sm text-muted-foreground">{loading ? "Đang tính…" : ""}</p>
        ) : (
          <>
            <div className="grid gap-3 text-sm sm:grid-cols-4">
              <Stat label="Đầu kỳ" value={forecast.opening_balance} sub={formatDate(forecast.start_date)} />
              <Stat
                label="Thấp nhất"
                value={forecast.min_balance}
                sub={formatDate(forecast.min_balance_day)}
                danger={forecast.min_balance < forecast.low_balance_threshold}
              />
              <Stat
                label="Cuối kỳ"
                value={forecast.end_balance}
                sub={formatDate(forecast.points[forecast.points.length - 1].date)}
              />
              <Stat
                label="Chi biến đổi / ngày"
                value={forecast.average_daily_variable_spending}
                sub={`${forecast.variable_history_days} ngày lịch sử`}
              />
            </div>

            {warning ? (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
              >
                <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
                <p>
                  Ngày <strong>{formatDate(warning)}</strong> số dư dự báo còn{" "}
                  <strong className="tabular-nums">
                    {formatVND(warningPoint?.projected_balance ?? 0)}
                  </strong>
                  , dưới ngưỡng {formatVND(forecast.low_balance_threshold)}. Nếu muốn giữ khoảng
                  đệm, bạn có thể xem lại các khoản sắp đến hạn trước ngày này.
                </p>
              </div>
            ) : (
              <p className="text-sm text-emerald-700 dark:text-emerald-400" role="status">
                Không có ngày nào số dư dự báo xuống dưới {formatVND(forecast.low_balance_threshold)}.
              </p>
            )}

            <div className="h-72 w-full" role="img" aria-label="Biểu đồ đường số dư dự báo">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={forecast.points} margin={{ left: 8, right: 16, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v: string) => formatDayMonth(v)}
                    fontSize={11}
                    minTickGap={16}
                  />
                  <YAxis
                    tickFormatter={(v: number) => compact.format(v)}
                    width={56}
                    fontSize={12}
                  />
                  <Tooltip content={<ForecastTooltip />} />
                  <ReferenceLine
                    y={forecast.low_balance_threshold}
                    stroke={WARNING_COLOR}
                    strokeDasharray="4 4"
                  />
                  <Line
                    type="monotone"
                    dataKey="projected_balance"
                    name="Số dư dự báo"
                    stroke={LINE_COLOR}
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  {warningPoint && (
                    <ReferenceDot
                      x={warningPoint.date}
                      y={warningPoint.projected_balance}
                      r={5}
                      fill={WARNING_COLOR}
                      stroke="white"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>

            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span aria-hidden className="h-0.5 w-4" style={{ backgroundColor: LINE_COLOR }} />
                Số dư dự báo
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  aria-hidden
                  className="h-0 w-4 border-t-2 border-dashed"
                  style={{ borderColor: WARNING_COLOR }}
                />
                Ngưỡng cảnh báo {formatVND(forecast.low_balance_threshold)}
              </span>
              {warningPoint && (
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="size-2.5 rounded-full"
                    style={{ backgroundColor: WARNING_COLOR }}
                  />
                  Ngày đầu tiên dưới ngưỡng
                </span>
              )}
            </p>

            <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
              {!forecast.starting_balance_set && (
                <li>Chưa nhập số dư hiện có — đường dự báo đang bắt đầu từ 0 ₫.</li>
              )}
              {forecast.insufficient_history && (
                <li>
                  Lịch sử chi tiêu dưới 30 ngày nên mức chi biến đổi trung bình chưa đáng tin
                  {forecast.average_daily_variable_spending === 0 ? " (đang tính là 0 ₫)" : ""}.
                </li>
              )}
              {forecast.overdue_recurring.length > 0 && (
                <li>
                  {forecast.overdue_recurring.length} khoản định kỳ đã quá hạn chưa ghi (
                  {forecast.overdue_recurring.map((o) => o.name).join(", ")}) — chưa tính vào dự
                  báo.
                </li>
              )}
              <li>
                Trong {forecast.days} ngày: thu định kỳ {formatVND(forecast.recurring_income_total)},
                chi định kỳ {formatVND(forecast.recurring_expense_total)}, để dành mục tiêu{" "}
                {formatVND(forecast.goal_saving_total)}, chi biến đổi ước tính{" "}
                {formatVND(forecast.variable_spending_total)}.
              </li>
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  sub,
  danger,
}: {
  label: string;
  value: number;
  sub: string;
  danger?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-muted/50 p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-lg font-semibold tabular-nums",
          danger && "text-rose-600 dark:text-rose-400",
        )}
      >
        {formatVND(value)}
      </span>
      <span className="text-xs text-muted-foreground">{sub}</span>
    </div>
  );
}
