"use client";

import { Suspense, useCallback, useState } from "react";

import { HomeMonthSummary } from "@/components/budget/home-month-summary";
import { QuickAddBox } from "@/components/quick-add/quick-add-box";

/** Quick add + tóm tắt tháng; lưu giao dịch xong thì tải lại tóm tắt. */
export function HomeDashboard() {
  const [version, setVersion] = useState(0);
  const handleSaved = useCallback(() => setVersion((v) => v + 1), []);

  return (
    <>
      <QuickAddBox onSaved={handleSaved} />
      <Suspense fallback={null}>
        <HomeMonthSummary key={version} />
      </Suspense>
    </>
  );
}
