import { SystemStatusCard } from "@/components/system-status-card";

export default function HomePage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Tổng quan</h1>
        <p className="text-sm text-muted-foreground">
          Khung ứng dụng đã sẵn sàng. Các tính năng sẽ được thêm dần theo từng
          phase.
        </p>
      </div>
      <SystemStatusCard />
    </div>
  );
}
