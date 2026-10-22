"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/** Error boundary toàn cục: lỗi render bất ngờ không làm trắng trang, cho phép thử lại. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
      <h1 className="font-heading text-xl font-semibold">Có lỗi khi hiển thị trang này</h1>
      <p className="text-sm text-muted-foreground">
        Dữ liệu của bạn không bị ảnh hưởng. Bạn có thể thử tải lại phần này; nếu lỗi vẫn còn,
        hãy kiểm tra backend đang chạy (`/api/v1/health`).
      </p>
      <Button onClick={reset}>Thử lại</Button>
    </div>
  );
}
