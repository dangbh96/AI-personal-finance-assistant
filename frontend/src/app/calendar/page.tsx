import type { Metadata } from "next";
import { Suspense } from "react";

import { CalendarPage } from "@/components/calendar/calendar-page";

export const metadata: Metadata = { title: "Lịch dòng tiền — Personal CFO" };

export default function Page() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}>
      <CalendarPage />
    </Suspense>
  );
}
