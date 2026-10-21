"use client";

import {
  PencilLineIcon,
  RefreshCwIcon,
  TriangleAlertIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ReceiptDetail } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import {
  LOW_RECEIPT_CONFIDENCE,
  RECEIPT_STATUS_CLASSES,
  RECEIPT_STATUS_LABELS,
} from "@/lib/receipts";
import { cn } from "@/lib/utils";

/** Kết quả AI đọc hoá đơn: cửa hàng, ngày, tổng, dòng hàng, độ tin cậy, cảnh báo, lỗi. */
export function ReceiptExtractionPanel({
  detail,
  onRetry,
  retrying = false,
  onManualEntry,
  manualOpen = false,
}: {
  detail: ReceiptDetail;
  onRetry?: () => void;
  retrying?: boolean;
  onManualEntry?: () => void;
  manualOpen?: boolean;
}) {
  const { receipt, extraction, status } = detail;
  const canRetry = status === "failed" || status === "uploaded";

  return (
    <section aria-label="Kết quả đọc hoá đơn" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={RECEIPT_STATUS_CLASSES[status]}>
          {RECEIPT_STATUS_LABELS[status]}
        </Badge>
        {extraction && <ConfidenceBadge confidence={extraction.confidence} />}
        {receipt.model && (
          <span className="text-xs text-muted-foreground">
            Đọc bởi {receipt.model}
          </span>
        )}
      </div>

      {status === "failed" && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <p className="flex gap-2">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
            <span>{receipt.error_message ?? "Chưa đọc được hoá đơn này."}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {canRetry && onRetry && (
              <Button
                size="sm"
                variant="outline"
                onClick={onRetry}
                disabled={retrying}
              >
                <RefreshCwIcon
                  data-icon="inline-start"
                  className={cn(retrying && "animate-spin")}
                />
                {retrying ? "Đang đọc lại…" : "Đọc lại"}
              </Button>
            )}
            {onManualEntry && !manualOpen && (
              <Button size="sm" onClick={onManualEntry}>
                <PencilLineIcon data-icon="inline-start" />
                Nhập thủ công từ ảnh này
              </Button>
            )}
          </div>
        </div>
      )}

      {extraction && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
          <Field label="Cửa hàng" value={extraction.merchant} />
          <Field
            label="Ngày"
            value={extraction.date ? formatDate(extraction.date) : null}
          />
          <Field
            label="Tổng thanh toán"
            value={totalLabel(extraction.total, extraction.currency)}
            strong
          />
          <Field label="Số dòng hàng" value={String(extraction.items.length)} />
        </dl>
      )}

      {extraction?.unreadable_reason && (
        <p className="text-sm text-muted-foreground">
          Lý do AI đưa ra: {extraction.unreadable_reason}
        </p>
      )}

      {extraction && extraction.items.length > 0 && (
        <details className="rounded-lg border" open={extraction.items.length <= 8}>
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
            Dòng hàng đọc được ({extraction.items.length})
          </summary>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tên</TableHead>
                <TableHead className="text-right">SL</TableHead>
                <TableHead className="text-right">Thành tiền</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {extraction.items.map((item, i) => (
                <TableRow key={`${item.name}-${i}`}>
                  <TableCell className="whitespace-normal">{item.name}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.qty ?? "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.amount !== null && item.amount !== undefined
                      ? formatVND(item.amount)
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      )}

      {detail.warnings.length > 0 && (
        <ul
          role="status"
          className="flex flex-col gap-1 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          {detail.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
              {w}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const VND_CODES = ["", "VND", "VNĐ", "Đ", "₫"];

/** Tổng hiển thị đúng như AI đọc; tiền khác VND không format thành đồng. */
function totalLabel(
  total: number | null | undefined,
  currency: string,
): string | null {
  if (total === null || total === undefined) return null;
  return VND_CODES.includes(currency.trim().toUpperCase())
    ? formatVND(total)
    : `${total} ${currency}`;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const percent = Math.round(confidence * 100);
  if (confidence < LOW_RECEIPT_CONFIDENCE) {
    return (
      <Badge
        variant="outline"
        className="border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300"
      >
        Độ tin cậy {percent}% — AI chưa chắc chắn
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className={cn(
        confidence >= 0.85 &&
          "border-emerald-300 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300",
      )}
    >
      Độ tin cậy {percent}%
    </Badge>
  );
}

function Field({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string | null | undefined;
  strong?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          "truncate",
          strong && "text-base font-semibold tabular-nums",
          !value && "text-muted-foreground",
        )}
      >
        {value || "Không đọc được"}
      </dd>
    </div>
  );
}
