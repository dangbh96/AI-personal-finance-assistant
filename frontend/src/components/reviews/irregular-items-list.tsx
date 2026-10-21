import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { MonthlyReviewMetrics } from "@/lib/api";
import { formatDate, formatSignedVND, formatVND } from "@/lib/format";

/** Khoản chi bất thường lớn nhất tháng — thường là khoản một lần, không phải thói quen. */
export function IrregularItemsList({ metrics }: { metrics: MonthlyReviewMetrics }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Khoản bất thường</CardTitle>
        <CardDescription>
          {metrics.increase_driver === "irregular"
            ? "Chi tăng so với tháng trước chủ yếu đến từ các khoản bất thường (khoản một lần)."
            : "Khoản không lặp lại hằng tháng — tách riêng để không nhầm với thói quen."}{" "}
          Tổng {formatVND(metrics.by_spending_type.irregular)}
          {metrics.irregular_change !== 0 &&
            ` (${formatSignedVND(metrics.irregular_change)} so với tháng trước)`}
          .
        </CardDescription>
      </CardHeader>
      <CardContent>
        {metrics.irregular_items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Tháng này không có khoản bất thường.</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {metrics.irregular_items.map((t) => (
              <li key={t.id} className="flex items-start justify-between gap-2">
                <span className="flex flex-col gap-0.5">
                  <span>{t.note ?? t.category_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.category_name} · {formatDate(t.occurred_on)}
                  </span>
                </span>
                <span className="tabular-nums">{formatVND(t.amount)}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
