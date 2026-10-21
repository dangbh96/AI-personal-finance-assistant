import type { Metadata } from "next";
import { Suspense } from "react";

import { WeeklyReviewPage } from "@/components/reviews/weekly-review-page";

export const metadata: Metadata = { title: "Review tuần — Personal CFO" };

async function WeeklyReviewRoute({ params }: { params: Promise<{ week: string }> }) {
  const { week } = await params;
  return <WeeklyReviewPage week={week} />;
}

export default function Page({ params }: { params: Promise<{ week: string }> }) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <WeeklyReviewRoute params={params} />
    </Suspense>
  );
}
