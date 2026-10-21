"use client";

import { io } from "next/cache";
import Link from "next/link";
import { use } from "react";

import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, type MonthlyReviewList } from "@/lib/api";
import { shiftMonth } from "@/lib/dates";
import { formatMonthLabel, formatPercent, formatVND } from "@/lib/format";

/** `/reviews/monthly`: lối tắt tháng trước / tháng này + các review tháng đã tạo. */
export function MonthlyReviewIndex() {
  use(io());
  const today = useReviewToday();
  const thisMonth = today.slice(0, 7);
  const lastMonth = shiftMonth(thisMonth, -1);
  const list = useApiData<MonthlyReviewList>("/reviews/monthly");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Review tháng</h1>
        <p className="text-sm text-muted-foreground">
          Bức tranh cả tháng: thu, chi, tiết kiệm, cơ cấu chi tiêu và ngân sách — để chuẩn bị cho
          tháng tới.{" "}
          <Link href="/reviews/weekly" className="underline underline-offset-3">
            Review tuần
          </Link>
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href={`/reviews/monthly/${lastMonth}`} className={buttonVariants()}>
          {formatMonthLabel(lastMonth)}
        </Link>
        <Link
          href={`/reviews/monthly/${thisMonth}`}
          className={buttonVariants({ variant: "outline" })}
        >
          {formatMonthLabel(thisMonth)} (đang chạy)
        </Link>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Review đã tạo</CardTitle>
        </CardHeader>
        <CardContent>
          {list.error && !list.data && (
            <p role="alert" className="text-sm text-destructive">
              {describeError(list.error)}
            </p>
          )}
          {list.data && list.data.items.length === 0 && (
            <p className="text-sm text-muted-foreground">Chưa có review tháng nào.</p>
          )}
          <ul className="flex flex-col divide-y">
            {list.data?.items.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reviews/monthly/${r.month.slice(0, 7)}`}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm hover:underline"
                >
                  <span className="flex items-center gap-2">
                    {formatMonthLabel(r.month.slice(0, 7))}
                    <Badge variant={r.status === "completed" ? "secondary" : "outline"}>
                      {r.status === "completed" ? "Đã phản tư" : "Chờ phản tư"}
                    </Badge>
                    {r.narrative.fallback_used && <Badge variant="outline">Bản tự động</Badge>}
                  </span>
                  <span className="text-muted-foreground tabular-nums">
                    Chi {formatVND(r.metrics.expense)} · tiết kiệm{" "}
                    {r.metrics.savings_rate_pct === null ||
                    r.metrics.savings_rate_pct === undefined
                      ? "—"
                      : formatPercent(r.metrics.savings_rate_pct)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
