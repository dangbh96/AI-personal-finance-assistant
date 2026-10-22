import type { Metadata } from "next";
import { Suspense } from "react";

import { SimulatorPage } from "@/components/simulator/simulator-page";

export const metadata: Metadata = { title: "Mô phỏng What-if — Personal CFO" };

export default function Page() {
  return (
    <Suspense
      fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}
    >
      <SimulatorPage />
    </Suspense>
  );
}
