"use client";

import { io } from "next/cache";
import Link from "next/link";
import { use } from "react";

import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, type WeeklyReviewList } from "@/lib/api";
import { addDays, formatWeekRange, weekStartOf } from "@/lib/dates";
import { formatVND } from "@/lib/format";

/** `/reviews/weekly`: lối tắt tuần trước / tuần này + các review đã tạo. */
export function WeeklyReviewIndex() {
  use(io());
  const today = useReviewToday();
  const thisWeek = weekStartOf(today);
  const lastWeek = addDays(thisWeek, -7);
  const list = useApiData<WeeklyReviewList>("/reviews/weekly");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Review tuần</h1>
        <p className="text-sm text-muted-foreground">
          Mỗi tuần nhìn lại chi tiêu: chuyện gì đã xảy ra, vì sao, điều gì đáng chú ý — rồi tự
          hỏi khoản nào chưa đáng tiền.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href={`/reviews/weekly/${lastWeek}`} className={buttonVariants()}>
          Tuần trước ({formatWeekRange(lastWeek)})
        </Link>
        <Link
          href={`/reviews/weekly/${thisWeek}`}
          className={buttonVariants({ variant: "outline" })}
        >
          Tuần này ({formatWeekRange(thisWeek)})
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
            <p className="text-sm text-muted-foreground">Chưa có review nào.</p>
          )}
          <ul className="flex flex-col divide-y">
            {list.data?.items.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/reviews/weekly/${r.week_start}`}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm hover:underline"
                >
                  <span className="flex items-center gap-2">
                    Tuần {formatWeekRange(r.week_start)}
                    <Badge variant={r.status === "completed" ? "secondary" : "outline"}>
                      {r.status === "completed" ? "Đã phản tư" : "Chờ phản tư"}
                    </Badge>
                    {r.narrative.fallback_used && (
                      <Badge variant="outline">Bản tự động</Badge>
                    )}
                  </span>
                  <span className="text-muted-foreground tabular-nums">
                    Chi {formatVND(r.metrics.expense)}
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
