import type { Metadata } from "next";
import { Suspense } from "react";

import { BudgetAdvicePage } from "@/components/budget-advice/budget-advice-page";

export const metadata: Metadata = { title: "Tư vấn ngân sách — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <BudgetAdvicePage />
    </Suspense>
  );
}
