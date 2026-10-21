import type { Metadata } from "next";
import { Suspense } from "react";

import { ImportPage } from "@/components/import/import-page";

export const metadata: Metadata = { title: "Nhập dữ liệu — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <ImportPage />
    </Suspense>
  );
}
