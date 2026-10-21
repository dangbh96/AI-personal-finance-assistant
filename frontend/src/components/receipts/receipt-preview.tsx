"use client";

import { ImageOffIcon } from "lucide-react";
import { useState } from "react";

import { formatFileSize } from "@/lib/receipts";

/** Ảnh hoá đơn đang xử lý (object URL local, hoặc ảnh backend — HEIC đã đổi sang JPEG). */
export function ReceiptPreview({
  src,
  filename,
  sizeBytes,
}: {
  src: string | null;
  filename: string;
  sizeBytes: number;
}) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const broken = src !== null && failedSrc === src;

  return (
    <figure className="flex flex-col gap-2">
      <div className="flex min-h-48 items-center justify-center overflow-hidden rounded-lg border bg-muted/40">
        {src && !broken ? (
          // Ảnh từ backend local (không qua next/image optimizer).
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={`Ảnh hoá đơn ${filename}`}
            className="mx-auto max-h-96 w-auto max-w-full object-contain"
            onError={() => setFailedSrc(src)}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 p-6 text-center text-sm text-muted-foreground">
            <ImageOffIcon className="size-6" aria-hidden />
            {broken
              ? "Không hiển thị được ảnh này."
              : "Trình duyệt chưa xem trước được ảnh HEIC — ảnh sẽ hiện sau khi tải lên."}
          </div>
        )}
      </div>
      <figcaption className="truncate text-xs text-muted-foreground">
        {filename} · {formatFileSize(sizeBytes)}
      </figcaption>
    </figure>
  );
}
