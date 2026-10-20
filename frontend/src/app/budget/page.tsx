import type { Metadata } from "next";
import { Suspense } from "react";

import { BudgetView } from "@/components/budget/budget-view";

export const metadata: Metadata = { title: "Ngân sách — Personal CFO" };

export default function BudgetPage() {
  return (
    <Suspense
      fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}
    >
      <BudgetView />
    </Suspense>
  );
}
