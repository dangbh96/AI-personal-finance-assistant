"use client";

import { FileSpreadsheetIcon, ShieldCheckIcon } from "lucide-react";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { IMPORT_ACCEPT_ATTR, validateImportFile } from "@/lib/imports";
import { cn } from "@/lib/utils";

/**
 * Bước 1: tên ngân hàng (tuỳ chọn, gợi ý từ mapping đã lưu) + kéo thả / chọn 1 file .csv / .xlsx.
 * Kiểm tra đuôi + dung lượng phía client trước khi gửi (backend vẫn kiểm tra lại).
 */
export function ImportUploadForm({
  bankName,
  onBankNameChange,
  bankSuggestions,
  onFile,
  disabled = false,
  progress = null,
}: {
  bankName: string;
  onBankNameChange: (value: string) => void;
  bankSuggestions: string[];
  onFile: (file: File) => void;
  disabled?: boolean;
  /** 0..1 khi đang upload; `1` = đã gửi xong, đang phân tích. */
  progress?: number | null;
}) {
  const bankId = useId();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pick(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    if (files && files.length > 1) {
      setError("Mỗi lần chỉ tải được 1 file sao kê.");
      return;
    }
    const problem = validateImportFile(file);
    setError(problem);
    if (!problem) onFile(file);
  }

  const percent = Math.round((progress ?? 0) * 100);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex max-w-sm flex-col gap-1.5">
        <Label htmlFor={bankId}>Ngân hàng (tuỳ chọn)</Label>
        <Input
          id={bankId}
          list={listId}
          maxLength={100}
          placeholder="Vietcombank, Techcombank…"
          value={bankName}
          disabled={disabled}
          onChange={(e) => onBankNameChange(e.target.value)}
        />
        <datalist id={listId}>
          {bankSuggestions.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <p className="text-xs text-muted-foreground">
          Dùng để nhớ cách map cột cho lần import sau của cùng ngân hàng.
        </p>
      </div>

      <div
        role="group"
        aria-label="Vùng tải file sao kê"
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
        <FileSpreadsheetIcon
          className="size-8 text-muted-foreground"
          aria-hidden
        />
        <div>
          <p className="font-medium">Kéo file sao kê vào đây</p>
          <p className="text-sm text-muted-foreground">
            .csv (UTF-8 / Windows-1258, dấu , ; hoặc tab) hoặc .xlsx · tối đa
            10MB
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={IMPORT_ACCEPT_ATTR}
          className="sr-only"
          aria-label="Chọn file sao kê"
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
          Chọn file
        </Button>

        {progress !== null && (
          <div className="w-full max-w-sm" aria-live="polite">
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              aria-label="Tiến độ tải file"
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
                ? `Đang tải file… ${percent}%`
                : "Đang đọc sao kê và gợi ý danh mục…"}
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
        Nội dung giao dịch (đã che số tài khoản / mã giao dịch dài) được gửi tới
        OpenAI để gợi ý danh mục; cột số dư không được gửi. Chưa có giao dịch
        nào được lưu cho tới khi bạn bấm nhập.
      </p>
    </div>
  );
}
