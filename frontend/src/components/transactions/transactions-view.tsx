"use client";

import { FileSpreadsheetIcon, PlusIcon, ReceiptTextIcon } from "lucide-react";
import { io } from "next/cache";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useEffect, useState } from "react";

import { PyfAllocationDialog } from "@/components/goals/pyf-allocation-dialog";
import { DeleteTransactionDialog } from "@/components/transactions/delete-transaction-dialog";
import {
  TransactionFilters,
  type Filters,
} from "@/components/transactions/transaction-filters";
import { TransactionFormDialog } from "@/components/transactions/transaction-form-dialog";
import { TransactionSummaryCards } from "@/components/transactions/transaction-summary-cards";
import { TransactionTable } from "@/components/transactions/transaction-table";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import {
  describeError,
  withQuery,
  type Category,
  type PyfProposal,
  type Transaction,
  type TransactionList,
  type TransactionSource,
  type TransactionSummary,
} from "@/lib/api";
import { currentMonth, monthToRange } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";
import { SOURCE_LABELS } from "@/lib/labels";

const PAGE_SIZE = 20;
const MONTH_PARAM = /^\d{4}-(0[1-9]|1[0-2])$/;
const UUID_PARAM = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type FormState = { open: boolean; transaction: Transaction | null };

function sourceParam(value: string | null): TransactionSource | null {
  return value && value in SOURCE_LABELS ? (value as TransactionSource) : null;
}

export function TransactionsView() {
  // Tháng mặc định phụ thuộc thời điểm hiện tại → không đưa vào static shell (Cache Components).
  use(io());
  // `?month=YYYY-MM` (vd link từ hoá đơn vừa lưu) chọn tháng ban đầu; `?source=import&
  // import_batch_id=…` (link sau khi import sao kê) lọc theo lô import, bỏ lọc tháng; `?q=` (link
  // từ trang tìm kiếm) điền sẵn ô tìm trong ghi chú.
  const params = useSearchParams();
  const monthParam = params.get("month");
  const batchParam = params.get("import_batch_id");
  const qParam = (params.get("q") ?? "").trim().slice(0, 100);
  const [filters, setFilters] = useState<Filters>(() => ({
    month:
      monthParam && MONTH_PARAM.test(monthParam) ? monthParam : currentMonth(),
    categoryId: null,
    spendingType: null,
    direction: null,
    q: qParam,
    source: sourceParam(params.get("source")),
    importBatchId: batchParam && UUID_PARAM.test(batchParam) ? batchParam : null,
  }));
  const [searchText, setSearchText] = useState(qParam);
  const [page, setPage] = useState(1);
  const [form, setForm] = useState<FormState>({ open: false, transaction: null });
  const [deleting, setDeleting] = useState<Transaction | null>(null);
  const [pyfProposal, setPyfProposal] = useState<PyfProposal | null>(null);

  // Debounce ô tìm kiếm.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((f) => (f.q === searchText.trim() ? f : { ...f, q: searchText.trim() }));
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchText]);

  const query = {
    ...(filters.importBatchId ? {} : monthToRange(filters.month)),
    category_id: filters.categoryId,
    spending_type: filters.spendingType,
    direction: filters.direction,
    q: filters.q,
    source: filters.source,
    import_batch_id: filters.importBatchId,
  };
  const categories = useApiData<Category[]>(
    withQuery("/categories", { include_archived: true }),
  );
  const list = useApiData<TransactionList>(
    withQuery("/transactions", { ...query, page, page_size: PAGE_SIZE }),
  );
  const summary = useApiData<TransactionSummary>(
    withQuery("/transactions/summary", query),
  );

  function changeFilters(patch: Partial<Filters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  }

  function reloadData() {
    list.reload();
    summary.reload();
  }

  const totalPages = list.data
    ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE))
    : 1;
  const error = list.error ?? summary.error ?? categories.error;
  const activeCategories = categories.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Giao dịch</h1>
          <p className="text-sm text-muted-foreground">
            {filters.importBatchId
              ? "Giao dịch từ một lô import sao kê"
              : formatMonthLabel(filters.month)}
            {list.data ? ` · ${list.data.total} giao dịch` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/import?tab=receipt"
            className={buttonVariants({ variant: "outline" })}
          >
            <ReceiptTextIcon data-icon="inline-start" />
            Nhập từ hoá đơn
          </Link>
          <Link
            href="/import?tab=csv"
            className={buttonVariants({ variant: "outline" })}
          >
            <FileSpreadsheetIcon data-icon="inline-start" />
            Nhập sao kê
          </Link>
          <Button
            onClick={() => setForm({ open: true, transaction: null })}
            disabled={!categories.data}
          >
            <PlusIcon data-icon="inline-start" />
            Thêm giao dịch
          </Button>
        </div>
      </div>

      <TransactionFilters
        filters={filters}
        categories={activeCategories}
        searchText={searchText}
        onSearchTextChange={setSearchText}
        onChange={changeFilters}
      />

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}

      <TransactionSummaryCards summary={summary.data} />

      <Card className="py-0">
        <CardContent
          className={list.loading && list.data ? "px-0 opacity-60" : "px-0"}
        >
          {list.data && list.data.items.length > 0 ? (
            <TransactionTable
              items={list.data.items}
              onEdit={(tx) => setForm({ open: true, transaction: tx })}
              onDelete={setDeleting}
            />
          ) : (
            <p className="p-8 text-center text-sm text-muted-foreground">
              {list.loading && !list.data
                ? "Đang tải…"
                : "Không có giao dịch nào khớp bộ lọc."}
            </p>
          )}
        </CardContent>
      </Card>

      {list.data && list.data.total > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">
            Trang {page}/{totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Trước
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Sau
          </Button>
        </div>
      )}

      <TransactionFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        categories={activeCategories}
        transaction={form.transaction}
        onSaved={reloadData}
        onPyfProposal={setPyfProposal}
      />
      <PyfAllocationDialog
        proposal={pyfProposal}
        onOpenChange={(open) => !open && setPyfProposal(null)}
      />
      <DeleteTransactionDialog
        transaction={deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        onDeleted={reloadData}
      />
    </div>
  );
}
