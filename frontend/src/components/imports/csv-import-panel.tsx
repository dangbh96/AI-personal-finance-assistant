"use client";

import {
  CircleCheckIcon,
  FileSpreadsheetIcon,
  RotateCcwIcon,
  TriangleAlertIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ImportMappingEditor } from "@/components/imports/import-mapping-editor";
import {
  ImportPreviewTable,
  type RowEdits,
} from "@/components/imports/import-preview-table";
import { ImportUploadForm } from "@/components/imports/import-upload-form";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import {
  ApiError,
  apiRequest,
  describeError,
  type Category,
  type ImportCommitRequest,
  type ImportCommitResult,
  type ImportConflict,
  type ImportMappingProfileList,
  type ImportMappingUpdate,
  type ImportPreview,
  type ImportPreviewRow,
} from "@/lib/api";
import { formatFileSize } from "@/lib/receipts";
import {
  ENCODING_LABELS,
  importTransactionsUrl,
  selectedByDefault,
  uploadImport,
} from "@/lib/imports";

type Uploading = { file: File; progress: number };
type Conflict = { message: string; batchId: string | null };

function initialEdits(rows: ImportPreviewRow[]): RowEdits {
  return Object.fromEntries(
    rows.map((row) => [
      row.row_index,
      {
        selected: selectedByDefault(row),
        categoryId: row.suggested_category_id ?? null,
        spendingType: row.suggested_spending_type ?? null,
        note: row.note,
      },
    ]),
  );
}

/**
 * Tab "Sao kê CSV / Excel" của `/import`: upload → mapping → xem trước + sửa (từng dòng / hàng
 * loạt) → nhập. Chỉ `POST /imports/{id}/commit` mới tạo giao dịch; frontend không tự đọc file hay
 * tính tiền — mọi số liệu lấy từ backend.
 */
export function CsvImportPanel() {
  const [bankName, setBankName] = useState("");
  const [uploading, setUploading] = useState<Uploading | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [edits, setEdits] = useState<RowEdits>({});
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [applying, setApplying] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState<ImportCommitResult | null>(null);

  const categories = useApiData<Category[]>("/categories");
  const profiles = useApiData<ImportMappingProfileList>(
    "/imports/mapping-profiles",
  );
  const bankSuggestions = [
    ...new Set(
      (profiles.data?.items ?? []).map((p) => p.bank_name).filter(Boolean),
    ),
  ];

  function show(next: ImportPreview) {
    setPreview(next);
    setEdits(initialEdits(next.rows));
    setError(null);
  }

  async function handleFile(file: File) {
    setPreview(null);
    setResult(null);
    setError(null);
    setConflict(null);
    setUploading({ file, progress: 0 });
    try {
      const body = await uploadImport(file, bankName, (progress) =>
        setUploading((u) => (u ? { ...u, progress } : u)),
      );
      show(body);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const body = err.body as ImportConflict | null;
        setConflict({
          message: err.message,
          batchId: body?.import_batch_id ?? null,
        });
      } else {
        setError(describeError(err));
      }
    } finally {
      setUploading(null);
    }
  }

  async function applyMapping(update: ImportMappingUpdate) {
    if (!preview) return;
    setApplying(true);
    setError(null);
    try {
      const next = await apiRequest<ImportPreview>(
        "PATCH",
        `/imports/${preview.batch.id}/mapping`,
        update,
      );
      show(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setApplying(false);
    }
  }

  const chosen = (preview?.rows ?? []).filter(
    (row) => row.status === "valid" && edits[row.row_index]?.selected,
  );
  const missingCategory = chosen.filter(
    (row) => !edits[row.row_index]?.categoryId,
  );

  async function commit() {
    if (!preview || chosen.length === 0 || missingCategory.length > 0) return;
    setCommitting(true);
    setError(null);
    const body: ImportCommitRequest = {
      save_mapping_profile: true,
      rows: chosen.map((row) => {
        const edit = edits[row.row_index];
        return {
          row_index: row.row_index,
          category_id: edit.categoryId as string,
          spending_type: row.direction === "expense" ? edit.spendingType : null,
          selected: true,
          ...(edit.note !== row.note ? { note: edit.note } : {}),
        };
      }),
    };
    try {
      const committed = await apiRequest<ImportCommitResult>(
        "POST",
        `/imports/${preview.batch.id}/commit`,
        body,
      );
      setResult(committed);
      setPreview({ ...preview, batch: committed.batch });
      profiles.reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setCommitting(false);
    }
  }

  function reset() {
    setPreview(null);
    setResult(null);
    setError(null);
    setConflict(null);
    setEdits({});
  }

  const committed = preview?.batch.status === "committed";

  return (
    <div className="flex flex-col gap-6">
      {!preview && (
        <ImportUploadForm
          bankName={bankName}
          onBankNameChange={setBankName}
          bankSuggestions={bankSuggestions}
          onFile={handleFile}
          disabled={uploading !== null}
          progress={uploading?.progress ?? null}
        />
      )}

      {uploading && (
        <p className="text-sm text-muted-foreground">
          {uploading.file.name} · {formatFileSize(uploading.file.size)}
        </p>
      )}

      {conflict && (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <p className="flex items-center gap-2 font-medium">
            <TriangleAlertIcon className="size-4" aria-hidden />
            File này đã được import
          </p>
          <p>{conflict.message}</p>
          {conflict.batchId && (
            <Link
              href={importTransactionsUrl(conflict.batchId)}
              className="font-medium underline underline-offset-4"
            >
              Xem các giao dịch đã import từ file này
            </Link>
          )}
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {preview && (
        <Card>
          <CardContent className="flex flex-col gap-6">
            <PreviewHeader preview={preview} />

            {preview.warnings.length > 0 && (
              <ul className="flex flex-col gap-1 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                {preview.warnings.map((warning) => (
                  <li key={warning} className="flex items-start gap-2">
                    <TriangleAlertIcon
                      className="mt-0.5 size-4 shrink-0"
                      aria-hidden
                    />
                    {warning}
                  </li>
                ))}
              </ul>
            )}

            <ImportMappingEditor
              key={`${preview.batch.id}-${preview.batch.updated_at}`}
              fileInfo={preview.file_info}
              mapping={preview.mapping}
              onApply={applyMapping}
              applying={applying}
              readOnly={committed}
            />

            {categories.data ? (
              <ImportPreviewTable
                key={`${preview.batch.id}-${preview.batch.updated_at}`}
                rows={preview.rows}
                edits={edits}
                onEditsChange={setEdits}
                categories={categories.data}
                readOnly={committed}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Đang tải danh mục…
              </p>
            )}

            {result ? (
              <CommitSummary result={result} />
            ) : committed ? (
              <p className="text-sm text-muted-foreground">
                Lô import này đã được nhập.
              </p>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                <p className="text-sm text-muted-foreground">
                  Sẽ tạo{" "}
                  <strong className="text-foreground">{chosen.length}</strong>{" "}
                  giao dịch · bỏ qua {preview.summary.duplicate_count} dòng
                  trùng, {preview.summary.bad_count} dòng lỗi
                  {missingCategory.length > 0 &&
                    ` · ${missingCategory.length} dòng chưa chọn danh mục`}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={reset}
                    disabled={committing}
                  >
                    Huỷ
                  </Button>
                  <Button
                    onClick={commit}
                    disabled={
                      committing ||
                      applying ||
                      chosen.length === 0 ||
                      missingCategory.length > 0
                    }
                  >
                    {committing
                      ? "Đang nhập…"
                      : `Nhập ${chosen.length} giao dịch`}
                  </Button>
                </div>
              </div>
            )}

            {(result || committed) && (
              <div className="flex justify-end">
                <Button variant="outline" onClick={reset}>
                  <RotateCcwIcon data-icon="inline-start" />
                  Nhập file khác
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PreviewHeader({ preview }: { preview: ImportPreview }) {
  const { batch, file_info: info, summary } = preview;
  const details = [
    info.file_type === "csv" ? "CSV" : "Excel",
    formatFileSize(info.size_bytes),
    info.encoding ? (ENCODING_LABELS[info.encoding] ?? info.encoding) : null,
    info.separator_label ? `phân cách bằng ${info.separator_label}` : null,
    info.sheet_name ? `sheet “${info.sheet_name}”` : null,
    `tiêu đề cột ở dòng ${info.header_row}`,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start gap-3">
        <FileSpreadsheetIcon
          className="mt-0.5 size-5 text-muted-foreground"
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p className="font-medium break-all">
            {batch.filename}
            {batch.bank_name ? ` · ${batch.bank_name}` : ""}
          </p>
          <p className="text-sm text-muted-foreground">{details.join(" · ")}</p>
          {info.warnings?.map((w) => (
            <p key={w} className="text-xs text-amber-700 dark:text-amber-300">
              {w}
            </p>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Tóm tắt các dòng">
        <Badge variant="outline">{summary.row_count} dòng</Badge>
        <Badge
          variant="outline"
          className="border-emerald-300 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300"
        >
          {summary.valid_count} hợp lệ
        </Badge>
        <Badge
          variant="outline"
          className="border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300"
        >
          {summary.duplicate_count} trùng
        </Badge>
        <Badge
          variant="outline"
          className="border-rose-300 text-rose-700 dark:border-rose-800 dark:text-rose-300"
        >
          {summary.bad_count} lỗi
        </Badge>
        {summary.preference_count > 0 && (
          <Badge variant="outline">
            ✨ {summary.preference_count} theo sở thích đã học
          </Badge>
        )}
        {summary.ai_count > 0 && (
          <Badge variant="outline">{summary.ai_count} do AI gợi ý</Badge>
        )}
        {summary.fallback_count > 0 && (
          <Badge variant="outline">
            {summary.fallback_count} chưa phân loại
          </Badge>
        )}
      </div>
    </div>
  );
}

function CommitSummary({ result }: { result: ImportCommitResult }) {
  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
    >
      <p className="flex items-center gap-2 font-medium">
        <CircleCheckIcon className="size-4" aria-hidden />
        Đã nhập {result.created_count} giao dịch
      </p>
      <ul className="list-inside list-disc">
        <li>Bỏ qua {result.skipped_duplicate_count} dòng trùng</li>
        <li>{result.bad_count} dòng lỗi không được nhập</li>
        {result.not_selected_count > 0 && (
          <li>{result.not_selected_count} dòng bạn đã bỏ chọn</li>
        )}
      </ul>
      <Link
        href={importTransactionsUrl(result.batch.id)}
        className={buttonVariants({ variant: "outline", className: "w-fit" })}
      >
        Xem giao dịch vừa nhập
      </Link>
    </div>
  );
}
