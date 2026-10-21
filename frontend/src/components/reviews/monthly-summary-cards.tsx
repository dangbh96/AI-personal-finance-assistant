import { StatCard } from "@/components/budget/month-summary-cards";
import { ChangeText } from "@/components/reviews/review-metric-cards";
import type { MonthlyReviewMetrics } from "@/lib/api";
import { formatPercent, formatSignedVND, formatVND } from "@/lib/format";

function SignedPct({ pct }: { pct: number }) {
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "±";
  return (
    <>
      {sign}
      {Math.abs(pct)}%
    </>
  );
}

/** Thu / Chi / Tiết kiệm / Tỉ lệ tiết kiệm của tháng — mọi số lấy nguyên từ API. */
export function MonthlySummaryCards({ metrics }: { metrics: MonthlyReviewMetrics }) {
  const rate = metrics.savings_rate_pct;
  const previousRate = metrics.previous_savings_rate_pct;
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Thu nhập"
        value={formatVND(metrics.income)}
        valueClassName="text-emerald-600"
      >
        {metrics.income_change_pct === null || metrics.income_change_pct === undefined ? (
          <span>Tháng trước chưa có thu nhập để so sánh</span>
        ) : (
          <span>
            <SignedPct pct={metrics.income_change_pct} /> so với tháng trước (
            {formatVND(metrics.previous_income)})
          </span>
        )}
      </StatCard>
      <StatCard label="Chi tiêu" value={formatVND(metrics.expense)} valueClassName="text-rose-600">
        <ChangeText
          pct={metrics.expense_change_pct}
          previous={metrics.previous_expense}
          periodWord="tháng"
        />
        <span>
          Thường xuyên {formatVND(metrics.regular_expense)}
          {metrics.regular_expense_change_pct !== null &&
            metrics.regular_expense_change_pct !== undefined && (
              <>
                {" "}
                (<SignedPct pct={metrics.regular_expense_change_pct} />)
              </>
            )}
        </span>
        <span>Bất thường {formatVND(metrics.by_spending_type.irregular)}</span>
      </StatCard>
      <StatCard
        label="Tiết kiệm (thu − chi)"
        value={formatVND(metrics.saved)}
        valueClassName={metrics.saved < 0 ? "text-rose-600" : undefined}
      >
        <span>Tháng trước {formatVND(metrics.previous_saved)}</span>
        {metrics.saved_change !== 0 && (
          <span>Chênh lệch {formatSignedVND(metrics.saved_change)}</span>
        )}
      </StatCard>
      <StatCard
        label="Tỉ lệ tiết kiệm"
        value={rate === null || rate === undefined ? "—" : formatPercent(rate)}
      >
        {rate === null || rate === undefined ? (
          <span>Tháng này chưa có thu nhập</span>
        ) : (
          <span>Tiết kiệm / thu nhập</span>
        )}
        {previousRate !== null && previousRate !== undefined && (
          <span>Tháng trước {formatPercent(previousRate)}</span>
        )}
        {!metrics.complete && (
          <span>
            Ngày {metrics.days_elapsed}/{metrics.days_in_period} — tháng chưa kết thúc
          </span>
        )}
      </StatCard>
    </div>
  );
}
