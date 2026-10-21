"use client";

import { CheckCircle2Icon, RotateCcwIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PyfAllocationDialog } from "@/components/goals/pyf-allocation-dialog";
import { ReceiptDraftForm } from "@/components/receipts/receipt-draft-form";
import { ReceiptExtractionPanel } from "@/components/receipts/receipt-extraction-panel";
import { ReceiptHistoryTable } from "@/components/receipts/receipt-history-table";
import { ReceiptPreview } from "@/components/receipts/receipt-preview";
import { ReceiptUploadDropzone } from "@/components/receipts/receipt-upload-dropzone";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiGet,
  apiRequest,
  describeError,
  withQuery,
  type Category,
  type PyfProposal,
  type ReceiptConfirmResult,
  type ReceiptDetail,
  type ReceiptList,
  type ReceiptStatus,
} from "@/lib/api";
import { todayISO } from "@/lib/dates";
import { formatDate, formatVND } from "@/lib/format";
import { describePreference } from "@/lib/labels";
import { canPreviewLocally, receiptFileUrl, uploadReceipt } from "@/lib/receipts";

type Current = {
  detail: ReceiptDetail;
  /** Object URL của file vừa chọn (xem trước trước khi backend trả ảnh). */
  localUrl: string | null;
};

type Uploading = { file: File; localUrl: string | null; progress: number };

/**
 * Tab "Hoá đơn" của `/import`: upload → AI đọc → draft (hoặc nhập tay) → user xác nhận mới lưu.
 * Frontend không tự tính tiền — mọi số lấy từ backend.
 */
export function ReceiptImportPanel() {
  const [uploading, setUploading] = useState<Uploading | null>(null);
  const [current, setCurrent] = useState<Current | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<ReceiptConfirmResult | null>(null);
  const [pyfProposal, setPyfProposal] = useState<PyfProposal | null>(null);
  const [statusFilter, setStatusFilter] = useState<ReceiptStatus | "all">("all");

  const categories = useApiData<Category[]>("/categories");
  const history = useApiData<ReceiptList>(
    withQuery("/receipts", {
      limit: 20,
      status: statusFilter === "all" ? null : statusFilter,
    }),
  );

  const localUrl = current?.localUrl ?? uploading?.localUrl ?? null;
  useEffect(() => {
    return () => {
      if (localUrl) URL.revokeObjectURL(localUrl);
    };
  }, [localUrl]);

  function show(detail: ReceiptDetail, url: string | null = null) {
    setCurrent({ detail, localUrl: url });
    setManualOpen(false);
    setSaved(null);
    setError(null);
  }

  async function handleFile(file: File) {
    const url = canPreviewLocally(file) ? URL.createObjectURL(file) : null;
    setCurrent(null);
    setSaved(null);
    setError(null);
    setUploading({ file, localUrl: url, progress: 0 });
    try {
      const detail = await uploadReceipt(file, todayISO(), (progress) =>
        setUploading((u) => (u ? { ...u, progress } : u)),
      );
      show(detail, url);
      history.reload();
    } catch (err) {
      if (url) URL.revokeObjectURL(url);
      setError(describeError(err));
    } finally {
      setUploading(null);
    }
  }

  async function retry() {
    if (!current) return;
    setRetrying(true);
    setError(null);
    try {
      const detail = await apiRequest<ReceiptDetail>(
        "POST",
        withQuery(`/receipts/${current.detail.receipt.id}/retry`, {
          today: todayISO(),
        }),
      );
      show(detail, current.localUrl);
      history.reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setRetrying(false);
    }
  }

  async function open(receiptId: string) {
    setError(null);
    try {
      const detail = await apiGet<ReceiptDetail>(
        withQuery(`/receipts/${receiptId}`, { today: todayISO() }),
      );
      show(detail);
    } catch (err) {
      setError(describeError(err));
    }
  }

  function handleSaved(result: ReceiptConfirmResult) {
    setSaved(result);
    if (result.pyf_proposal) setPyfProposal(result.pyf_proposal);
    setCurrent((c) =>
      c
        ? {
            ...c,
            detail: {
              ...c.detail,
              status: "confirmed",
              receipt: result.receipt,
              transaction: result.transaction,
              manual_prefill: null,
            },
          }
        : c,
    );
    history.reload();
  }

  function reset() {
    setCurrent(null);
    setSaved(null);
    setError(null);
    setManualOpen(false);
  }

  const detail = current?.detail ?? null;
  const showForm =
    detail !== null &&
    detail.status !== "confirmed" &&
    (detail.status === "extracted" || manualOpen);

  return (
    <div className="flex flex-col gap-6">
      {!detail && (
        <ReceiptUploadDropzone
          onFile={handleFile}
          disabled={uploading !== null}
          progress={uploading?.progress ?? null}
        />
      )}

      {uploading && (
        <div className="max-w-sm">
          <ReceiptPreview
            src={uploading.localUrl}
            filename={uploading.file.name}
            sizeBytes={uploading.file.size}
          />
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {detail && (
        <Card>
          <CardContent className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <ReceiptPreview
              key={detail.receipt.id}
              src={current?.localUrl ?? receiptFileUrl(detail.receipt.id)}
              filename={detail.receipt.original_filename}
              sizeBytes={detail.receipt.file_size_bytes}
            />
            <div className="flex min-w-0 flex-col gap-4">
              <ReceiptExtractionPanel
                detail={detail}
                onRetry={retry}
                retrying={retrying}
                onManualEntry={() => setManualOpen(true)}
                manualOpen={manualOpen}
              />

              {showForm && categories.data && (
                <ReceiptDraftForm
                  key={`${detail.receipt.id}-${detail.receipt.updated_at}`}
                  detail={detail}
                  categories={categories.data}
                  onSaved={handleSaved}
                />
              )}

              {detail.status === "confirmed" && (
                <SavedNotice detail={detail} saved={saved} />
              )}

              <div className="flex justify-end">
                <Button variant="outline" onClick={reset}>
                  <RotateCcwIcon data-icon="inline-start" />
                  Tải hoá đơn khác
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <ReceiptHistoryTable
        items={history.data?.items}
        loading={history.loading}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        onOpen={open}
        activeId={detail?.receipt.id ?? null}
      />

      <PyfAllocationDialog
        proposal={pyfProposal}
        onOpenChange={(isOpen) => !isOpen && setPyfProposal(null)}
      />
    </div>
  );
}

function SavedNotice({
  detail,
  saved,
}: {
  detail: ReceiptDetail;
  saved: ReceiptConfirmResult | null;
}) {
  const tx = saved?.transaction ?? detail.transaction;
  return (
    <div
      role="status"
      className="flex flex-col gap-1 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
    >
      <p className="flex items-center gap-2 font-medium">
        <CheckCircle2Icon className="size-4" aria-hidden />
        {saved ? "Đã lưu giao dịch từ hoá đơn" : "Hoá đơn này đã được lưu thành giao dịch"}
      </p>
      {tx ? (
        <p>
          {tx.note ?? tx.category.name} · {formatVND(tx.amount)} ·{" "}
          {formatDate(tx.occurred_on)} ·{" "}
          <Link
            href={`/transactions?month=${tx.occurred_on.slice(0, 7)}`}
            className="font-medium underline underline-offset-4"
          >
            Xem trong Giao dịch
          </Link>
        </p>
      ) : (
        <p>Giao dịch đã bị xoá sau khi lưu.</p>
      )}
      {saved?.learned_preference && (
        <p className="text-xs">
          ✨ Đã học cách phân loại cửa hàng này:{" "}
          {describePreference(saved.learned_preference)}
        </p>
      )}
    </div>
  );
}
