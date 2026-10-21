import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatMonthLabel } from "@/lib/format";

export const metadata: Metadata = { title: "Tư vấn ngân sách — Personal CFO" };

const MONTH_START = /^(\d{4}-(0[1-9]|1[0-2]))-01$/;

/** Chỗ đặt trước cho Budget adjustment advisor (Phase 8) — đích của CTA ở review tháng. */
async function BudgetAdvice({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const { month } = await searchParams;
  const ym = month && MONTH_START.exec(month)?.[1];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Tư vấn điều chỉnh ngân sách</h1>
        <p className="text-sm text-muted-foreground">
          {ym ? `Dựa trên số liệu ${formatMonthLabel(ym).toLowerCase()}.` : "Chọn tháng từ review tháng."}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Sắp có (Phase 8)</CardTitle>
          <CardDescription>
            Với mỗi dòng ngân sách lệch kế hoạch, app sẽ phân biệt: nên chỉnh ngân sách, chỉnh thói
            quen, hay chỉ là khoản một lần — kèm số liệu làm căn cứ để bạn quyết định.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {ym && (
            <Link href={`/reviews/monthly/${ym}`} className={buttonVariants({ variant: "outline" })}>
              Quay lại review {formatMonthLabel(ym).toLowerCase()}
            </Link>
          )}
          <Link
            href={ym ? `/budget?month=${ym}&tab=track` : "/budget"}
            className={buttonVariants({ variant: "outline" })}
          >
            Xem ngân sách
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export default function BudgetAdvicePage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <BudgetAdvice searchParams={searchParams} />
    </Suspense>
  );
}
