import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { MonthlyReviewMetrics } from "@/lib/api";
import { formatWeekRange } from "@/lib/dates";
import { formatVND } from "@/lib/format";

/** Tóm tắt phản tư của các review tuần trong tháng (tuần có Thứ Hai thuộc tháng). */
export function WeeklyReflectionDigest({ metrics }: { metrics: MonthlyReviewMetrics }) {
  const digest = metrics.weekly_reflections;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Phản tư các tuần</CardTitle>
        <CardDescription>
          {metrics.flagged_count > 0
            ? `Bạn đã đánh dấu ${metrics.flagged_count} khoản chưa đáng tiền, tổng ${formatVND(metrics.flagged_total)}.`
            : "Những gì bạn đã ghi lại trong các review tuần của tháng."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {digest.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Chưa có phản tư tuần nào trong tháng.{" "}
            <Link href="/reviews/weekly" className="underline underline-offset-3">
              Mở review tuần
            </Link>
          </p>
        ) : (
          <ul className="flex flex-col gap-3 text-sm">
            {digest.map((d) => (
              <li key={d.reflection_id} className="flex flex-col gap-1">
                <Link
                  href={`/reviews/weekly/${d.week_start}`}
                  className="text-xs font-medium text-muted-foreground hover:underline"
                >
                  Tuần {formatWeekRange(d.week_start)}
                </Link>
                {d.answer && <p>“{d.answer}”</p>}
                {d.flagged.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Không đáng tiền:{" "}
                    {d.flagged
                      .map((f) => `${f.note ?? f.category_name} (${formatVND(f.amount)})`)
                      .join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
