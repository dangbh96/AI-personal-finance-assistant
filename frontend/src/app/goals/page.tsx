import type { Metadata } from "next";
import { Suspense } from "react";

import { GoalsPage } from "@/components/goals/goals-page";

export const metadata: Metadata = { title: "Mục tiêu — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <GoalsPage />
    </Suspense>
  );
}
