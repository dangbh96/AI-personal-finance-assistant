"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AIUsagePanel } from "@/components/settings/ai-usage-panel";
import { CategoryManager } from "@/components/settings/category-manager";
import { PreferenceManager } from "@/components/settings/preference-manager";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TABS = ["categories", "preferences", "ai-usage"] as const;
type Tab = (typeof TABS)[number];

/** Tab đang mở lưu ở `?tab=` để link được (vd từ thông báo "Đã học cách phân loại này"). */
export function SettingsTabs() {
  const router = useRouter();
  const pathname = usePathname();
  const param = useSearchParams().get("tab");
  const tab: Tab = TABS.includes(param as Tab) ? (param as Tab) : "categories";

  return (
    <Tabs
      value={tab}
      onValueChange={(value) =>
        router.replace(`${pathname}?tab=${value}`, { scroll: false })
      }
      className="gap-4"
    >
      <TabsList>
        <TabsTrigger value="categories">Danh mục</TabsTrigger>
        <TabsTrigger value="preferences">Sở thích phân loại</TabsTrigger>
        <TabsTrigger value="ai-usage">Chi phí AI</TabsTrigger>
      </TabsList>
      <TabsContent value="categories">
        <CategoryManager />
      </TabsContent>
      <TabsContent value="preferences">
        <PreferenceManager />
      </TabsContent>
      <TabsContent value="ai-usage">
        <AIUsagePanel />
      </TabsContent>
    </Tabs>
  );
}
