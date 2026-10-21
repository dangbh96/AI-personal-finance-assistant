"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ReceiptImportPanel } from "@/components/receipts/receipt-import-panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TABS = ["receipt"] as const;
type Tab = (typeof TABS)[number];

/** `/import`: tab "Hoá đơn" (Phase 13); tab sao kê CSV / Excel có từ Phase 14. Tab lưu ở `?tab=`. */
export function ImportPage() {
  const router = useRouter();
  const pathname = usePathname();
  const param = useSearchParams().get("tab");
  const tab: Tab = TABS.includes(param as Tab) ? (param as Tab) : "receipt";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Nhập dữ liệu</h1>
        <p className="text-sm text-muted-foreground">
          Tạo giao dịch từ ảnh hoá đơn — AI đọc giúp, bạn kiểm tra rồi mới lưu.
        </p>
      </div>
      <Tabs
        value={tab}
        onValueChange={(value) =>
          router.replace(`${pathname}?tab=${value}`, { scroll: false })
        }
        className="gap-4"
      >
        <TabsList>
          <TabsTrigger value="receipt">Hoá đơn</TabsTrigger>
          <TabsTrigger value="csv" disabled title="Có từ Phase 14">
            Sao kê CSV / Excel
          </TabsTrigger>
        </TabsList>
        <TabsContent value="receipt">
          <ReceiptImportPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
