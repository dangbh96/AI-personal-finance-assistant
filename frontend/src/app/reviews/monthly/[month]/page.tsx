import type { Metadata } from "next";
import { Suspense } from "react";

import { MonthlyReviewPage } from "@/components/reviews/monthly-review-page";

export const metadata: Metadata = { title: "Review tháng — Personal CFO" };

async function MonthlyReviewRoute({ params }: { params: Promise<{ month: string }> }) {
  const { month } = await params;
  return <MonthlyReviewPage month={month} />;
}

export default function Page({ params }: { params: Promise<{ month: string }> }) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <MonthlyReviewRoute params={params} />
    </Suspense>
  );
}
