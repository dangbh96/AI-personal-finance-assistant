import type { Metadata } from "next";
import { Suspense } from "react";

import { WeeklyReviewIndex } from "@/components/reviews/weekly-review-index";

export const metadata: Metadata = { title: "Review tuần — Personal CFO" };

export default function WeeklyReviewsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <WeeklyReviewIndex />
    </Suspense>
  );
}
