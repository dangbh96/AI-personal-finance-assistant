import { StatCard } from "@/components/budget/month-summary-cards";
import type { ReviewMetrics } from "@/lib/api";
import { formatDate, formatSignedVND, formatVND } from "@/lib/format";
import { SPENDING_TYPE_LABELS, SPENDING_TYPES } from "@/lib/labels";

/** "+18% so với tuần trước" — % do backend tính, frontend chỉ thêm dấu. */
export function ChangeText({
  pct,
  previous,
  periodWord = "tuần",
}: {
  pct: number | null | undefined;
  previous: number;
  periodWord?: string;
}) {
  if (pct === null || pct === undefined) {
    return <span>{periodWord[0].toUpperCase() + periodWord.slice(1)} trước chưa có khoản chi để so sánh</span>;
  }
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "±";
  return (
    <span>
      {sign}
      {Math.abs(pct)}% so với {periodWord} trước ({formatVND(previous)})
    </span>
  );
}

/** Thẻ số liệu tuần — mọi số lấy nguyên từ `metrics` của backend. */
export function ReviewMetricCards({ metrics }: { metrics: ReviewMetrics }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Chi tiêu" value={formatVND(metrics.expense)}>
        <ChangeText pct={metrics.expense_change_pct} previous={metrics.previous_expense} />
        {metrics.expense_change !== 0 && (
          <span>Chênh lệch {formatSignedVND(metrics.expense_change)}</span>
        )}
      </StatCard>
      <StatCard label="Thu nhập" value={formatVND(metrics.income)}>
        <span>Thu − chi: {formatSignedVND(metrics.net)}</span>
      </StatCard>
      <StatCard label="Theo loại chi tiêu" value={`${metrics.expense_count} khoản chi`}>
        {SPENDING_TYPES.map((type) => (
          <span key={type} className="flex justify-between gap-2">
            <span>{SPENDING_TYPE_LABELS[type]}</span>
            <span className="tabular-nums">{formatVND(metrics.by_spending_type[type])}</span>
          </span>
        ))}
      </StatCard>
      <StatCard
        label="Kỳ review"
        value={
          metrics.complete
            ? "Đã kết thúc"
            : `Ngày ${metrics.days_elapsed}/${metrics.days_in_period}`
        }
      >
        <span>
          {formatDate(metrics.period_start)} – {formatDate(metrics.period_end)}
        </span>
        {!metrics.complete && <span>Số liệu tính đến {formatDate(metrics.as_of)}</span>}
      </StatCard>
    </div>
  );
}
