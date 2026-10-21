"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { MonthlyReviewMetrics } from "@/lib/api";
import { formatPercent, formatVND } from "@/lib/format";
import { SPENDING_TYPE_COLORS, SPENDING_TYPE_LABELS, SPENDING_TYPES } from "@/lib/labels";

const compact = new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 });
const PREVIOUS_COLOR = "#cbd5e1";

function tooltipVND(value: unknown): string {
  return typeof value === "number" ? formatVND(value) : String(value);
}

/** Cơ cấu chi theo spending type (pie) + so với tháng trước (bar). Chỉ vẽ số từ API. */
export function SpendingTypeChart({ metrics }: { metrics: MonthlyReviewMetrics }) {
  const rows = SPENDING_TYPES.map((type) => ({
    type,
    label: SPENDING_TYPE_LABELS[type],
    amount: metrics.by_spending_type[type],
    previous: metrics.previous_by_spending_type[type],
    pct: metrics.spending_type_pct[type],
  }));
  const pieData = rows.filter((r) => r.amount > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cơ cấu chi tiêu</CardTitle>
        <CardDescription>
          Thiết yếu / Không thiết yếu / Bất thường — tháng này và so với tháng trước.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-2">
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">Tháng này</h3>
          {pieData.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có khoản chi.</p>
          ) : (
            <div className="h-56 w-full" role="img" aria-label="Biểu đồ tròn cơ cấu chi tiêu">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="amount"
                    nameKey="label"
                    innerRadius="55%"
                    outerRadius="85%"
                    paddingAngle={2}
                    isAnimationActive={false}
                  >
                    {pieData.map((r) => (
                      <Cell key={r.type} fill={SPENDING_TYPE_COLORS[r.type]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={tooltipVND} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <ul className="flex flex-col gap-1 text-sm">
            {rows.map((r) => (
              <li key={r.type} className="grid grid-cols-[1fr_auto_3.5rem] items-center gap-2">
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: SPENDING_TYPE_COLORS[r.type] }}
                  />
                  <span>{r.label}</span>
                </span>
                <span className="text-right tabular-nums">{formatVND(r.amount)}</span>
                <span className="text-right text-muted-foreground tabular-nums">
                  {r.pct === null || r.pct === undefined ? "—" : formatPercent(r.pct)}
                </span>
              </li>
            ))}
          </ul>
        </section>
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-medium">So với tháng trước</h3>
          <div className="h-64 w-full" role="img" aria-label="Biểu đồ cột so với tháng trước">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ left: 8, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tickLine={false} interval={0} fontSize={11} />
                <YAxis
                  tickFormatter={(v: number) => compact.format(v)}
                  width={48}
                  fontSize={12}
                />
                <Tooltip formatter={tooltipVND} />
                <Bar
                  dataKey="previous"
                  name="Tháng trước"
                  fill={PREVIOUS_COLOR}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
                <Bar dataKey="amount" name="Tháng này" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {rows.map((r) => (
                    <Cell key={r.type} fill={SPENDING_TYPE_COLORS[r.type]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <span
              aria-hidden
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: PREVIOUS_COLOR }}
            />
            Tháng trước · cột màu: tháng này
          </p>
        </section>
      </CardContent>
    </Card>
  );
}
