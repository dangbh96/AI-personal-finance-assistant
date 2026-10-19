import type { Metadata } from "next";
import { Suspense } from "react";

import { SettingsTabs } from "@/components/settings/settings-tabs";

export const metadata: Metadata = { title: "Cài đặt — Personal CFO" };

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Cài đặt</h1>
        <p className="text-sm text-muted-foreground">
          Quản lý danh mục và cách AI phân loại chi tiêu theo ý bạn.
        </p>
      </div>
      <Suspense
        fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}
      >
        <SettingsTabs />
      </Suspense>
    </div>
  );
}
