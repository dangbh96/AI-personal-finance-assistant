"use client";

import { useState } from "react";

import {
  AllocationPreviewTable,
  BudgetWarnings,
  ReferenceComparison,
} from "@/components/budget/allocation-preview-table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useBudgetPreview } from "@/hooks/use-budget-preview";
import {
  apiRequest,
  describeError,
  type Budget,
  type BudgetJar,
  type BudgetPreviewRequest,
  type BudgetStatus,
  type BudgetUpdate,
} from "@/lib/api";
import {
  STATUS_CLASSES,
  STATUS_LABELS,
  STRATEGY_LABELS,
  parseBudgetAmount,
  toAllocationInputs,
  toRows,
  type AllocationRow,
} from "@/lib/budget";
import { formatAmountPlain, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

type StatusAction = { to: BudgetStatus; label: string; primary?: boolean };

const STATUS_ACTIONS: Record<BudgetStatus, StatusAction[]> = {
  draft: [{ to: "active", label: "Kích hoạt", primary: true }],
  active: [
    { to: "draft", label: "Chuyển về nháp" },
    { to: "closed", label: "Đóng tháng" },
  ],
  closed: [{ to: "active", label: "Mở lại" }],
};

function sameAmounts(a: AllocationRow[], b: AllocationRow[]): boolean {
  return a.every(
    (row, i) =>
      parseBudgetAmount(row.amountText) === parseBudgetAmount(b[i].amountText),
  );
}

/**
 * Xem / chỉnh ngân sách đã lưu. Mount lại (đổi `key`) sau mỗi lần lưu để state khớp backend.
 */
export function BudgetEditor({
  budget,
  jars,
  onChanged,
  onDeleted,
}: {
  budget: Budget;
  jars: BudgetJar[] | undefined;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const initialRows = toRows(budget.allocations);
  const [incomeText, setIncomeText] = useState(
    formatAmountPlain(budget.expected_income),
  );
  const [rows, setRows] = useState(initialRows);
  const [confirmOver, setConfirmOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const readOnly = budget.status === "closed";
  const income = parseBudgetAmount(incomeText);
  const inputs = toAllocationInputs(rows);
  const dirty =
    income !== budget.expected_income || !sameAmounts(rows, initialRows);

  let request: BudgetPreviewRequest | null = null;
  if (dirty && income !== null && inputs) {
    request = {
      period_month: budget.period_month,
      strategy: budget.strategy,
      expected_income: income,
      allocations: inputs,
    };
  }
  const preview = useBudgetPreview(request);
  const shown = dirty
    ? (preview.fresh ?? (preview.loading ? preview.data : undefined))
    : undefined;
  const totals = dirty ? shown?.budget.totals : budget.totals;
  const reference = dirty
    ? shown?.reference_50_30_20
    : budget.reference_50_30_20;
  // Bỏ cảnh báo "tháng đã có ngân sách" — chính là ngân sách đang sửa.
  const warnings = (
    dirty
      ? (preview.fresh?.warnings ?? [])
      : budget.totals.unallocated < 0
        ? [
            {
              code: "planned_exceeds_income",
              message: `Tổng phân bổ vượt thu nhập dự kiến ${formatVND(-budget.totals.unallocated)}.`,
            },
          ]
        : []
  ).filter((w) => w.code !== "budget_exists");
  const overIncome =
    dirty && warnings.some((w) => w.code === "planned_exceeds_income");
  const canSave =
    dirty && !!preview.fresh && (!overIncome || confirmOver) && !busy;

  async function patch(body: BudgetUpdate) {
    setBusy(true);
    setError(null);
    try {
      await apiRequest<Budget>("PATCH", `/budgets/${budget.id}`, body);
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setBusy(true);
    setError(null);
    try {
      await apiRequest<void>("DELETE", `/budgets/${budget.id}`);
      setConfirmDelete(false);
      onDeleted();
    } catch (err) {
      setError(describeError(err));
      setConfirmDelete(false);
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="pb-0">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2">
            {STRATEGY_LABELS[budget.strategy]}
            <span
              className={cn(
                "inline-flex h-5 items-center rounded-4xl px-2 text-xs font-medium",
                STATUS_CLASSES[budget.status],
              )}
            >
              {STATUS_LABELS[budget.status]}
            </span>
          </CardTitle>
          <CardDescription>
            {readOnly
              ? "Ngân sách đã đóng — mở lại để chỉnh sửa."
              : "Sửa thu nhập dự kiến hoặc số tiền từng dòng rồi bấm “Lưu thay đổi”."}
          </CardDescription>
          <CardAction className="flex flex-wrap justify-end gap-2">
            {STATUS_ACTIONS[budget.status].map((action) => (
              <Button
                key={action.to}
                size="sm"
                variant={action.primary ? "default" : "outline"}
                disabled={busy || dirty}
                title={dirty ? "Lưu hoặc huỷ thay đổi trước" : undefined}
                onClick={() => patch({ status: action.to })}
              >
                {action.label}
              </Button>
            ))}
            {budget.status === "draft" && (
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => setConfirmDelete(true)}
              >
                Xoá nháp
              </Button>
            )}
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 px-0">
          <div className="grid gap-4 px-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="budget-edit-income">Thu nhập dự kiến</Label>
              {readOnly ? (
                <span className="tabular-nums">
                  {formatVND(budget.expected_income)}
                </span>
              ) : (
                <Input
                  id="budget-edit-income"
                  inputMode="numeric"
                  value={incomeText}
                  aria-invalid={income === null}
                  onChange={(e) => setIncomeText(e.target.value)}
                />
              )}
              {income === null && (
                <span className="text-xs text-destructive">
                  Số tiền không hợp lệ
                </span>
              )}
            </div>
            {budget.savings_target !== null && (
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Tiết kiệm</span>
                <span className="tabular-nums">
                  {formatVND(
                    dirty && shown
                      ? shown.budget.savings_target
                      : budget.savings_target,
                  )}
                </span>
              </div>
            )}
          </div>
          {warnings.length > 0 && (
            <div className="px-4">
              <BudgetWarnings warnings={warnings} />
            </div>
          )}
          {preview.error && (
            <p role="alert" className="px-4 text-sm text-destructive">
              {describeError(preview.error)}
            </p>
          )}
          <AllocationPreviewTable
            rows={rows}
            readOnly={readOnly}
            onAmountChange={(index, text) =>
              setRows((prev) =>
                prev.map((r, i) =>
                  i === index ? { ...r, amountText: text } : r,
                ),
              )
            }
            totals={totals}
            expectedIncome={income}
            jars={jars}
            stale={dirty && preview.loading}
          />
        </CardContent>
      </Card>

      {!readOnly && (
        <div className="flex flex-col gap-3">
          {overIncome && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4"
                checked={confirmOver}
                onChange={(e) => setConfirmOver(e.target.checked)}
              />
              Tôi biết tổng phân bổ đang vượt thu nhập dự kiến và vẫn muốn lưu
            </label>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!canSave}
              onClick={() =>
                income !== null &&
                inputs &&
                patch({
                  expected_income: income,
                  allocations: inputs,
                  confirm_over_income: confirmOver,
                })
              }
            >
              {busy ? "Đang lưu…" : "Lưu thay đổi"}
            </Button>
            <Button
              variant="outline"
              disabled={!dirty || busy}
              onClick={() => {
                setRows(initialRows);
                setIncomeText(formatAmountPlain(budget.expected_income));
                setConfirmOver(false);
                setError(null);
              }}
            >
              Huỷ thay đổi
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>So với mốc 50/30/20</CardTitle>
        </CardHeader>
        <CardContent>
          <ReferenceComparison reference={reference} />
        </CardContent>
      </Card>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Xoá ngân sách nháp này?</AlertDialogTitle>
            <AlertDialogDescription>
              Toàn bộ phân bổ của tháng sẽ bị xoá. Thao tác này không hoàn tác
              được.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
              disabled={busy}
            >
              Xoá
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
