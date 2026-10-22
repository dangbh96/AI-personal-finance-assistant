"use client";

import { AlertTriangleIcon, SparklesIcon } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
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
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { GoalImpact, SimulationResult } from "@/lib/api";
import { formatDate, formatSignedVND, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

const BEFORE_COLOR = "#cbd5e1";
const AFTER_COLOR = "#0ea5e9";
const months = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });

function deltaTone(value: number): string {
  if (value > 0) return "text-emerald-600 dark:text-emerald-400";
  if (value < 0) return "text-red-600 dark:text-red-400";
  return "text-muted-foreground";
}

/** Toàn bộ kết quả mô phỏng — chỉ hiển thị số backend đã tính. */
export function SimulationResults({ result }: { result: SimulationResult }) {
  return (
    <div className="flex flex-col gap-4">
      <BeforeAfterCards result={result} />
      {result.narrative && <NarrativeCard result={result} />}
      {result.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          {result.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
              {w}
            </li>
          ))}
        </ul>
      )}
      <GoalImpactCard goals={result.goal_impacts} />
      {result.budget_variance_after.length > 0 && (
        <BudgetVarianceTable result={result} />
      )}
      {result.category_changes.length > 0 && (
        <CategoryChangesTable result={result} />
      )}
    </div>
  );
}

function BeforeAfterCards({ result }: { result: SimulationResult }) {
  const cards = [
    {
      title: "Để dành / tháng hiện tại",
      value: formatVND(result.baseline_monthly_savings),
    },
    {
      title: "Để dành / tháng theo kịch bản",
      value: formatVND(result.projected_monthly_savings),
    },
    {
      title: "Chênh lệch / tháng",
      value: formatSignedVND(result.delta_monthly_savings),
      tone: deltaTone(result.delta_monthly_savings),
    },
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-3 sm:grid-cols-3">
        {cards.map((c) => (
          <Card key={c.title} size="sm">
            <CardHeader>
              <CardTitle className="text-sm font-normal text-muted-foreground">
                {c.title}
              </CardTitle>
            </CardHeader>
            <CardContent
              className={cn("text-xl font-semibold tabular-nums", c.tone)}
            >
              {c.value}
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Mức nền: trung bình {result.baseline_months} tháng (
        {formatDate(result.baseline_from)} – {formatDate(result.baseline_to)}
        {result.include_irregular
          ? ", tính cả khoản bất thường"
          : ", không tính khoản bất thường"}
        ). Thu {formatVND(result.baseline_monthly_income)} →{" "}
        {formatVND(result.projected_monthly_income)} · Chi{" "}
        {formatVND(result.baseline_monthly_expense)} →{" "}
        {formatVND(result.projected_monthly_expense)}
      </p>
      <div className="flex flex-wrap gap-2">
        {result.applied.map((a) => (
          <Badge key={a.index} variant="outline">
            {a.label}
            {a.delta_monthly_savings !== 0 && (
              <span className={cn("ml-1", deltaTone(a.delta_monthly_savings))}>
                {formatSignedVND(a.delta_monthly_savings)}
              </span>
            )}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function NarrativeCard({ result }: { result: SimulationResult }) {
  const n = result.narrative!;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SparklesIcon className="size-4" />
          Diễn giải
          <Badge variant="secondary">
            {result.narrative_source === "ai" ? "AI" : "Bản tự động"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2 text-sm leading-relaxed">
        <p>
          <span className="font-medium">Quan sát: </span>
          {n.observation}
        </p>
        <p>
          <span className="font-medium">Vì sao: </span>
          {n.explanation}
        </p>
        {n.action && (
          <p>
            <span className="font-medium">Bạn có thể cân nhắc: </span>
            {n.action}
          </p>
        )}
        {n.caveats.length > 0 && (
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {n.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function completion(goal: GoalImpact, when: "before" | "after"): string {
  const date =
    when === "before"
      ? goal.completion_date_before
      : goal.completion_date_after;
  const days = when === "before" ? goal.days_before : goal.days_after;
  const m = when === "before" ? goal.months_before : goal.months_after;
  if (!date || days === null || days === undefined)
    return "Không đạt (không còn tiền để dành)";
  return `${formatDate(date)} · ${days} ngày (${months.format(m ?? 0)} tháng)`;
}

function GoalImpactCard({ goals }: { goals: GoalImpact[] }) {
  if (goals.length === 0) return null;
  const data = goals.map((g) => ({
    name: g.name,
    before: g.days_before ?? 0,
    after: g.days_after ?? 0,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Mục tiêu</CardTitle>
        <CardDescription>
          Tiền để dành mỗi tháng dồn cho mục tiêu theo thứ tự ưu tiên; 1 tháng =
          30 ngày.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          className="h-48 w-full"
          role="img"
          aria-label="Biểu đồ số ngày đạt mục tiêu trước và sau"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 16, right: 16 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" fontSize={12} unit=" ngày" />
              <YAxis type="category" dataKey="name" width={96} fontSize={12} />
              <Tooltip formatter={(v) => `${v} ngày`} />
              <Legend />
              <Bar
                dataKey="before"
                name="Hiện tại"
                fill={BEFORE_COLOR}
                isAnimationActive={false}
              />
              <Bar
                dataKey="after"
                name="Theo kịch bản"
                fill={AFTER_COLOR}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mục tiêu</TableHead>
              <TableHead className="text-right">Còn thiếu</TableHead>
              <TableHead>Hiện tại</TableHead>
              <TableHead>Theo kịch bản</TableHead>
              <TableHead>Thay đổi</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {goals.map((g) => (
              <TableRow key={g.goal_id}>
                <TableCell className="font-medium">
                  {g.name}
                  <span className="block text-xs text-muted-foreground">
                    Hạn {formatDate(g.deadline_after)}
                    {g.deadline_after !== g.deadline_before &&
                      ` (cũ ${formatDate(g.deadline_before)})`}
                    {" · "}
                    {g.on_track_after ? "kịp hạn" : "chưa kịp hạn"}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(g.remaining_amount)}
                </TableCell>
                <TableCell className="text-sm">
                  {completion(g, "before")}
                </TableCell>
                <TableCell className="text-sm">
                  {completion(g, "after")}
                </TableCell>
                <TableCell
                  className={cn(
                    "text-sm font-medium",
                    deltaTone(g.days_earlier ?? 0),
                  )}
                >
                  {g.days_earlier === null || g.days_earlier === undefined
                    ? "—"
                    : g.days_earlier > 0
                      ? `Sớm hơn ${g.days_earlier} ngày`
                      : g.days_earlier < 0
                        ? `Muộn hơn ${-g.days_earlier} ngày`
                        : "Không đổi"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function BudgetVarianceTable({ result }: { result: SimulationResult }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>So với ngân sách</CardTitle>
        <CardDescription>
          Ngân sách tháng{" "}
          {result.budget_month ? formatDate(result.budget_month).slice(3) : ""}{" "}
          so với chi trung bình / tháng (chênh lệch dương = vượt).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Dòng</TableHead>
              <TableHead className="text-right">Ngân sách</TableHead>
              <TableHead className="text-right">Chi hiện tại</TableHead>
              <TableHead className="text-right">Chi theo kịch bản</TableHead>
              <TableHead className="text-right">
                Chênh lệch trước → sau
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.budget_variance_after.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="font-medium">{row.label}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(row.planned)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(row.baseline_actual)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(row.projected_actual)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  <span className={deltaTone(-row.variance_before)}>
                    {formatSignedVND(row.variance_before)}
                  </span>
                  {" → "}
                  <span className={deltaTone(-row.variance_after)}>
                    {formatSignedVND(row.variance_after)}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CategoryChangesTable({ result }: { result: SimulationResult }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Chi tiêu theo danh mục thay đổi</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableBody>
            {result.category_changes.map((c) => (
              <TableRow key={`${c.category_id}-${c.name}`}>
                <TableCell>{c.name}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatVND(c.baseline)} → {formatVND(c.projected)}
                </TableCell>
                <TableCell
                  className={cn("text-right tabular-nums", deltaTone(-c.delta))}
                >
                  {formatSignedVND(c.delta)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
