import type { Metadata } from "next";
import { Suspense } from "react";

import { MonthlyReviewIndex } from "@/components/reviews/monthly-review-index";

export const metadata: Metadata = { title: "Review tháng — Personal CFO" };

export default function MonthlyReviewsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <MonthlyReviewIndex />
    </Suspense>
  );
}
