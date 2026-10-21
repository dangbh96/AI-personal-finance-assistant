import type { Metadata } from "next";
import { Suspense } from "react";

import { CoachPage } from "@/components/coach/coach-page";

export const metadata: Metadata = { title: "Financial Coach — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <CoachPage />
    </Suspense>
  );
}
