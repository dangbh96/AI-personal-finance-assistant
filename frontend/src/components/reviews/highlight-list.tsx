import { SpendingTypeBadge } from "@/components/spending-type-badge";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CategoryChange, ReviewHighlights } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";

function ChangeBadge({ change }: { change: CategoryChange }) {
  if (change.change_pct === null || change.change_pct === undefined) {
    return change.previous_amount === 0 ? <Badge variant="outline">Mới</Badge> : null;
  }
  if (change.change_pct === 0) return <Badge variant="outline">±0%</Badge>;
  return (
    <Badge variant={change.change_pct > 0 ? "destructive" : "secondary"}>
      {change.change_pct > 0 ? "+" : "−"}
      {Math.abs(change.change_pct)}%
    </Badge>
  );
}

/** Evidence của narrative: danh mục chi nhiều, nhóm lặp lại, khoản chi lớn. */
export function HighlightList({ highlights }: { highlights: ReviewHighlights }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Số liệu làm căn cứ</CardTitle>
        <CardDescription>
          Tính sẵn từ giao dịch của bạn — AI chỉ được dùng các số này.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 md:grid-cols-3">
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Danh mục chi nhiều nhất</h3>
          {highlights.top_categories.length === 0 && (
            <p className="text-sm text-muted-foreground">Chưa có khoản chi.</p>
          )}
          <ul className="flex flex-col gap-2 text-sm">
            {highlights.top_categories.map((c) => (
              <li key={c.category_id} className="flex items-center justify-between gap-2">
                <span>
                  {c.icon} {c.name}
                </span>
                <span className="flex items-center gap-2 tabular-nums">
                  {formatVND(c.amount)}
                  <ChangeBadge change={c} />
                </span>
              </li>
            ))}
          </ul>
          {highlights.top_increase && (
            <p className="text-xs text-muted-foreground">
              Tăng nhiều nhất: {highlights.top_increase.name} (+
              {formatVND(highlights.top_increase.change)})
            </p>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Khoản lặp lại</h3>
          {highlights.repeated_clusters.length === 0 && (
            <p className="text-sm text-muted-foreground">Không có nhóm nào lặp từ 3 lần.</p>
          )}
          <ul className="flex flex-col gap-2 text-sm">
            {highlights.repeated_clusters.map((c) => (
              <li key={c.key} className="flex items-center justify-between gap-2">
                <span>
                  {c.count} lần · {c.label}
                </span>
                <span className="tabular-nums">{formatVND(c.total)}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Khoản chi lớn nhất</h3>
          {highlights.top_transactions.length === 0 && (
            <p className="text-sm text-muted-foreground">Chưa có khoản chi.</p>
          )}
          <ul className="flex flex-col gap-2 text-sm">
            {highlights.top_transactions.map((t) => (
              <li key={t.id} className="flex items-start justify-between gap-2">
                <span className="flex flex-col gap-0.5">
                  <span>{t.note ?? t.category_name}</span>
                  <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                    {t.category_name} · {formatDate(t.occurred_on)}
                    {t.spending_type && <SpendingTypeBadge value={t.spending_type} />}
                  </span>
                </span>
                <span className="tabular-nums">{formatVND(t.amount)}</span>
              </li>
            ))}
          </ul>
        </section>
      </CardContent>
    </Card>
  );
}
