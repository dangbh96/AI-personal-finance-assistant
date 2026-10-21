"use client";

import { ImageUpIcon, ShieldCheckIcon } from "lucide-react";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { RECEIPT_ACCEPT_ATTR, validateReceiptFile } from "@/lib/receipts";
import { cn } from "@/lib/utils";

/**
 * Kéo thả / chọn 1 ảnh hoá đơn. Kiểm tra loại + dung lượng phía client trước khi gửi
 * (backend vẫn kiểm tra lại). Dưới vùng thả luôn có ghi chú quyền riêng tư.
 */
export function ReceiptUploadDropzone({
  onFile,
  disabled = false,
  progress = null,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
  /** 0..1 khi đang upload; `1` = đã gửi xong, đang chờ AI đọc. */
  progress?: number | null;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pick(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    if (files && files.length > 1) {
      setError("Mỗi lần chỉ tải được 1 ảnh hoá đơn.");
      return;
    }
    const problem = validateReceiptFile(file);
    setError(problem);
    if (!problem) onFile(file);
  }

  const percent = Math.round((progress ?? 0) * 100);

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Vùng tải ảnh hoá đơn"
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) pick(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-border",
          disabled && "opacity-60",
        )}
      >
        <ImageUpIcon className="size-8 text-muted-foreground" aria-hidden />
        <div>
          <p className="font-medium">Kéo ảnh hoá đơn vào đây</p>
          <p className="text-sm text-muted-foreground">
            JPEG, PNG, WEBP hoặc HEIC · tối đa 10MB · 1 ảnh mỗi lần
          </p>
        </div>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={RECEIPT_ACCEPT_ATTR}
          className="sr-only"
          aria-label="Chọn ảnh hoá đơn"
          disabled={disabled}
          onChange={(e) => {
            pick(e.target.files);
            e.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
        >
          Chọn ảnh
        </Button>

        {progress !== null && (
          <div className="w-full max-w-sm" aria-live="polite">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              aria-label="Tiến độ tải ảnh"
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div
                className={cn(
                  "h-full bg-primary transition-[width]",
                  percent >= 100 && "animate-pulse",
                )}
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {percent < 100
                ? `Đang tải ảnh… ${percent}%`
                : "AI đang đọc hoá đơn…"}
            </p>
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <ShieldCheckIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        Ảnh được lưu local và gửi tới OpenAI để đọc nội dung hoá đơn; không dùng
        cho mục đích khác trong app.
      </p>
    </div>
  );
}
