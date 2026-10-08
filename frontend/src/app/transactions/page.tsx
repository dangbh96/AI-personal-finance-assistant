import type { Metadata } from "next";
import { Suspense } from "react";

import { TransactionsView } from "@/components/transactions/transactions-view";

export const metadata: Metadata = { title: "Giao dịch — Personal CFO" };

export default function TransactionsPage() {
  return (
    <Suspense
      fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}
    >
      <TransactionsView />
    </Suspense>
  );
}
