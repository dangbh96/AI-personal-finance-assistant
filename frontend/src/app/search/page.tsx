import type { Metadata } from "next";
import { Suspense } from "react";

import { SearchPage } from "@/components/search/search-page";

export const metadata: Metadata = { title: "Tìm kiếm — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <SearchPage />
    </Suspense>
  );
}
