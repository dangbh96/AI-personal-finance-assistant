"use client";

import {
  ArrowRightLeftIcon,
  CopyIcon,
  SparklesIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useId, useState } from "react";

import { NATIVE_SELECT_CLASS } from "@/components/imports/import-mapping-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  Category,
  ImportPreviewRow,
  ImportRowStatus,
  SpendingType,
} from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import {
  foldText,
  IMPORT_ROW_STATUS_CLASSES,
  IMPORT_ROW_STATUS_LABELS,
  PREVIEW_PAGE_SIZE,
} from "@/lib/imports";
import { SPENDING_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

export type RowEdit = {
  selected: boolean;
  categoryId: string | null;
  spendingType: SpendingType | null;
  note: string;
};

export type RowEdits = Record<number, RowEdit>;

type StatusFilter = ImportRowStatus | "all" | "warning";

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "valid", label: "Hợp lệ" },
  { value: "warning", label: "Cần xem lại" },
  { value: "duplicate", label: "Trùng" },
  { value: "bad", label: "Lỗi" },
];

function matchesStatus(row: ImportPreviewRow, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "warning")
    return row.status === "valid" && (row.warnings ?? []).length > 0;
  return row.status === filter;
}

function CategoryOptions({ categories }: { categories: Category[] }) {
  return categories.map((c) => (
    <option key={c.id} value={c.id}>
      {`${c.icon ?? ""} ${c.name}`.trim()}
    </option>
  ));
}

/**
 * Bước 3: bảng xem trước. Checkbox = dòng sẽ được nhập; sửa danh mục / loại chi tiêu / ghi chú
 * từng dòng hoặc hàng loạt cho các dòng **đang chọn trong danh sách lọc**. Số tiền / ngày / chiều
 * thu chi lấy nguyên từ backend, không sửa ở đây.
 */
export function ImportPreviewTable({
  rows,
  edits,
  onEditsChange,
  categories,
  readOnly = false,
}: {
  rows: ImportPreviewRow[];
  edits: RowEdits;
  onEditsChange: (update: (edits: RowEdits) => RowEdits) => void;
  categories: Category[];
  readOnly?: boolean;
}) {
  const idPrefix = useId();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [limit, setLimit] = useState(PREVIEW_PAGE_SIZE);
  const [bulkCategory, setBulkCategory] = useState("");
  const [bulkSpending, setBulkSpending] = useState<SpendingType | "">("");
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);

  const active = categories.filter((c) => !c.is_archived);
  const expenseCategories = active.filter((c) => c.kind === "expense");
  const incomeCategories = active.filter((c) => c.kind === "income");
  const byId = new Map(categories.map((c) => [c.id, c]));

  const folded = foldText(query.trim());
  const filtered = rows.filter(
    (row) =>
      matchesStatus(row, statusFilter) &&
      (!folded || foldText(row.note).includes(folded)),
  );
  const shown = filtered.slice(0, limit);
  const selectable = filtered.filter((row) => row.status === "valid");
  const selectedInView = selectable.filter(
    (row) => edits[row.row_index]?.selected,
  );
  const allChecked =
    selectable.length > 0 && selectedInView.length === selectable.length;

  function update(rowIndex: number, patch: Partial<RowEdit>) {
    onEditsChange((current) => ({
      ...current,
      [rowIndex]: { ...current[rowIndex], ...patch },
    }));
  }

  function toggleAll(checked: boolean) {
    onEditsChange((current) => {
      const next = { ...current };
      for (const row of selectable) {
        next[row.row_index] = { ...next[row.row_index], selected: checked };
      }
      return next;
    });
  }

  function changeCategory(row: ImportPreviewRow, categoryId: string) {
    const category = byId.get(categoryId);
    update(row.row_index, {
      categoryId: categoryId || null,
      spendingType:
        row.direction === "expense"
          ? (category?.default_spending_type ?? null)
          : null,
    });
  }

  function applyBulk() {
    const category = bulkCategory ? byId.get(bulkCategory) : undefined;
    const targets = selectedInView.filter(
      (row) => !category || category.kind === row.direction,
    );
    const skipped = selectedInView.length - targets.length;
    onEditsChange((current) => {
      const next = { ...current };
      for (const row of targets) {
        const patch: Partial<RowEdit> = {};
        if (category) {
          patch.categoryId = category.id;
          patch.spendingType =
            row.direction === "expense"
              ? (category.default_spending_type ?? null)
              : null;
        }
        if (bulkSpending && row.direction === "expense") {
          patch.spendingType = bulkSpending;
        }
        next[row.row_index] = { ...next[row.row_index], ...patch };
      }
      return next;
    });
    setBulkMessage(
      `Đã áp dụng cho ${targets.length} dòng` +
        (skipped ? ` (bỏ qua ${skipped} dòng khác loại thu / chi)` : "") +
        ".",
    );
  }

  return (
    <section aria-label="Xem trước các dòng" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-56 flex-1 flex-col gap-1">
          <Label htmlFor={`${idPrefix}-q`}>Lọc theo nội dung</Label>
          <Input
            id={`${idPrefix}-q`}
            type="search"
            placeholder="Ví dụ: grab"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setBulkMessage(null);
            }}
          />
        </div>
        <div
          role="radiogroup"
          aria-label="Lọc theo trạng thái"
          className="flex flex-wrap gap-1"
        >
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.value}
              size="sm"
              role="radio"
              aria-checked={statusFilter === f.value}
              variant={statusFilter === f.value ? "secondary" : "ghost"}
              onClick={() => {
                setStatusFilter(f.value);
                setBulkMessage(null);
              }}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {!readOnly && (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-muted/40 p-3">
          <p className="w-full text-sm">
            Sửa hàng loạt <strong>{selectedInView.length}</strong> dòng đang
            chọn
            {folded || statusFilter !== "all" ? " trong danh sách đã lọc" : ""}:
          </p>
          <div className="flex min-w-48 flex-col gap-1">
            <Label htmlFor={`${idPrefix}-bulk-category`}>Danh mục</Label>
            <select
              id={`${idPrefix}-bulk-category`}
              className={NATIVE_SELECT_CLASS}
              value={bulkCategory}
              onChange={(e) => setBulkCategory(e.target.value)}
            >
              <option value="">— Giữ nguyên —</option>
              <optgroup label="Chi tiêu">
                <CategoryOptions categories={expenseCategories} />
              </optgroup>
              <optgroup label="Thu nhập">
                <CategoryOptions categories={incomeCategories} />
              </optgroup>
            </select>
          </div>
          <div className="flex min-w-40 flex-col gap-1">
            <Label htmlFor={`${idPrefix}-bulk-spending`}>Loại chi tiêu</Label>
            <select
              id={`${idPrefix}-bulk-spending`}
              className={NATIVE_SELECT_CLASS}
              value={bulkSpending}
              onChange={(e) =>
                setBulkSpending(e.target.value as SpendingType | "")
              }
            >
              <option value="">— Theo danh mục —</option>
              {Object.entries(SPENDING_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="secondary"
            disabled={
              selectedInView.length === 0 || (!bulkCategory && !bulkSpending)
            }
            onClick={applyBulk}
          >
            Áp dụng cho {selectedInView.length} dòng
          </Button>
          {bulkMessage && (
            <p role="status" className="text-sm text-muted-foreground">
              {bulkMessage}
            </p>
          )}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                {!readOnly && (
                  <input
                    type="checkbox"
                    aria-label="Chọn tất cả dòng hợp lệ đang hiển thị"
                    className="size-4 accent-primary"
                    checked={allChecked}
                    disabled={selectable.length === 0}
                    onChange={(e) => toggleAll(e.target.checked)}
                  />
                )}
              </TableHead>
              <TableHead className="w-12">Dòng</TableHead>
              <TableHead>Ngày</TableHead>
              <TableHead className="min-w-48">Nội dung</TableHead>
              <TableHead className="text-right">Số tiền</TableHead>
              <TableHead className="w-44 min-w-40">Phân loại</TableHead>
              <TableHead>Trạng thái</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {shown.map((row) => {
              const edit = edits[row.row_index];
              const valid = row.status === "valid";
              const editable = valid && !readOnly;
              const options =
                row.direction === "income"
                  ? incomeCategories
                  : expenseCategories;
              return (
                <TableRow
                  key={row.row_index}
                  className={cn(
                    !valid && "text-muted-foreground",
                    valid && !edit?.selected && "opacity-70",
                  )}
                >
                  <TableCell>
                    {!readOnly && (
                      <input
                        type="checkbox"
                        aria-label={`Nhập dòng ${row.row_index}`}
                        className="size-4 accent-primary"
                        checked={valid && !!edit?.selected}
                        disabled={!valid}
                        onChange={(e) =>
                          update(row.row_index, { selected: e.target.checked })
                        }
                      />
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {row.row_index}
                  </TableCell>
                  <TableCell className="tabular-nums whitespace-nowrap">
                    {row.occurred_on
                      ? formatDate(row.occurred_on)
                      : (row.raw.date ?? "—")}
                  </TableCell>
                  <TableCell className="max-w-80 whitespace-normal">
                    {editable ? (
                      <Input
                        aria-label={`Ghi chú dòng ${row.row_index}`}
                        maxLength={500}
                        value={edit?.note ?? row.note}
                        onChange={(e) =>
                          update(row.row_index, { note: e.target.value })
                        }
                        title={row.note}
                      />
                    ) : (
                      <span className="break-words">{row.note || "—"}</span>
                    )}
                    <RowNotes row={row} />
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-medium tabular-nums whitespace-nowrap",
                      row.direction === "income" && "text-emerald-600",
                      row.direction === "expense" && "text-rose-600",
                    )}
                  >
                    {row.amount !== null && row.amount !== undefined
                      ? `${row.direction === "income" ? "+" : "−"}${formatVND(row.amount)}`
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1.5">
                      {valid ? (
                        <select
                          aria-label={`Danh mục dòng ${row.row_index}`}
                          className={NATIVE_SELECT_CLASS}
                          disabled={readOnly}
                          value={edit?.categoryId ?? ""}
                          onChange={(e) => changeCategory(row, e.target.value)}
                        >
                          <option value="">— Chọn danh mục —</option>
                          <CategoryOptions categories={options} />
                        </select>
                      ) : (
                        "—"
                      )}
                      {valid && row.direction === "expense" && (
                        <select
                          aria-label={`Loại chi tiêu dòng ${row.row_index}`}
                          className={NATIVE_SELECT_CLASS}
                          disabled={readOnly}
                          value={edit?.spendingType ?? ""}
                          onChange={(e) =>
                            update(row.row_index, {
                              spendingType: (e.target.value ||
                                null) as SpendingType | null,
                            })
                          }
                        >
                          <option value="">— Loại theo danh mục —</option>
                          {Object.entries(SPENDING_TYPE_LABELS).map(
                            ([value, label]) => (
                              <option key={value} value={value}>
                                {label}
                              </option>
                            ),
                          )}
                        </select>
                      )}
                      {valid && row.suggestion_source === "preference" && (
                        <p className="flex items-center gap-1 text-xs text-sky-700 dark:text-sky-300">
                          <SparklesIcon className="size-3" aria-hidden />
                          Theo sở thích đã học
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={IMPORT_ROW_STATUS_CLASSES[row.status]}
                    >
                      {row.status === "duplicate" && <CopyIcon aria-hidden />}
                      {IMPORT_ROW_STATUS_LABELS[row.status]}
                    </Badge>
                    {valid &&
                      row.confidence !== null &&
                      row.confidence !== undefined && (
                        <p
                          className={cn(
                            "mt-1 text-xs tabular-nums",
                            row.confidence < 0.6
                              ? "text-amber-700 dark:text-amber-300"
                              : "text-muted-foreground",
                          )}
                          title={row.reason ?? undefined}
                        >
                          Độ tin cậy {Math.round(row.confidence * 100)}%
                        </p>
                      )}
                  </TableCell>
                </TableRow>
              );
            })}
            {shown.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="p-6 text-center text-muted-foreground"
                >
                  Không có dòng nào khớp bộ lọc.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>
          Hiển thị {shown.length}/{filtered.length} dòng
          {filtered.length !== rows.length ? ` (tổng ${rows.length})` : ""}
        </span>
        {filtered.length > shown.length && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLimit((l) => l + PREVIEW_PAGE_SIZE)}
          >
            Hiện thêm{" "}
            {Math.min(PREVIEW_PAGE_SIZE, filtered.length - shown.length)} dòng
          </Button>
        )}
      </div>
    </section>
  );
}

function RowNotes({ row }: { row: ImportPreviewRow }) {
  const notes: { icon: React.ReactNode; text: string; tone: string }[] = [];
  if (row.error) {
    notes.push({
      icon:
        row.status === "duplicate" ? (
          <CopyIcon className="size-3" aria-hidden />
        ) : (
          <TriangleAlertIcon className="size-3" aria-hidden />
        ),
      text: row.error,
      tone:
        row.status === "bad"
          ? "text-rose-700 dark:text-rose-300"
          : "text-amber-700 dark:text-amber-300",
    });
  }
  for (const warning of row.warnings ?? []) {
    notes.push({
      icon:
        row.transfer_hint && warning.includes("chuyển khoản") ? (
          <ArrowRightLeftIcon className="size-3" aria-hidden />
        ) : (
          <TriangleAlertIcon className="size-3" aria-hidden />
        ),
      text: warning,
      tone: "text-amber-700 dark:text-amber-300",
    });
  }
  if (
    row.status === "valid" &&
    row.reason &&
    row.suggestion_source !== "preference"
  ) {
    notes.push({ icon: null, text: row.reason, tone: "text-muted-foreground" });
  }
  if (notes.length === 0) return null;
  return (
    <ul className="mt-1 flex flex-col gap-0.5 text-xs">
      {notes.map((note, i) => (
        <li key={i} className={cn("flex items-start gap-1", note.tone)}>
          {note.icon && <span className="mt-0.5 shrink-0">{note.icon}</span>}
          <span>{note.text}</span>
        </li>
      ))}
    </ul>
  );
}
