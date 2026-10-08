import Link from "next/link";

import { SystemStatusCard } from "@/components/system-status-card";

export default function HomePage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Tổng quan</h1>
        <p className="text-sm text-muted-foreground">
          Ghi chép thu chi thủ công đã sẵn sàng ở mục{" "}
          <Link href="/transactions" className="underline underline-offset-3">
            Giao dịch
          </Link>
          . Các tính năng khác sẽ được thêm dần theo từng phase.
        </p>
      </div>
      <SystemStatusCard />
    </div>
  );
}
