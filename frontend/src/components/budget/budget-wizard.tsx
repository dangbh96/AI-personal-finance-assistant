"use client";

import { CopyIcon, RotateCcwIcon } from "lucide-react";
import { io } from "next/cache";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";

import {
  AllocationPreviewTable,
  BudgetWarnings,
  ReferenceComparison,
} from "@/components/budget/allocation-preview-table";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiData } from "@/hooks/use-api-data";
import { useBudgetPreview } from "@/hooks/use-budget-preview";
import {
  ApiError,
  apiRequest,
  describeError,
  type Budget,
  type BudgetCopyRequest,
  type BudgetCreate,
  type BudgetJarList,
  type BudgetPreviewRequest,
  type BudgetStatus,
  type BudgetStrategy,
} from "@/lib/api";
import {
  STRATEGIES,
  STRATEGY_DESCRIPTIONS,
  STRATEGY_LABELS,
  monthToPeriod,
  parseBudgetAmount,
  toAllocationInputs,
  toRows,
  type AllocationRow,
} from "@/lib/budget";
import { currentMonth } from "@/lib/dates";
import { formatMonthLabel, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

type SaveError = { message: string; budgetExists: boolean };

function AmountField({
  id,
  label,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const amount = parseBudgetAmount(value);
  const invalid = value.trim() !== "" && amount === null;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="numeric"
        placeholder={placeholder}
        value={value}
        aria-invalid={invalid}
        onChange={(e) => onChange(e.target.value)}
      />
      <span
        className={cn(
          "text-xs",
          invalid ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {invalid
          ? "Số tiền không hợp lệ"
          : amount !== null
            ? `= ${formatVND(amount)}`
            : "Gõ tắt được: 25tr, 25 triệu, 25.000.000"}
      </span>
    </div>
  );
}

/** Tạo ngân sách tháng: chọn chiến lược → backend tính phân bổ → user chỉnh → lưu. */
export function BudgetWizard() {
  // Tháng mặc định phụ thuộc thời điểm hiện tại → không đưa vào static shell (Cache Components).
  use(io());
  const router = useRouter();
  const monthParam = useSearchParams().get("month");
  const [month, setMonth] = useState(() =>
    monthParam && MONTH_PATTERN.test(monthParam) ? monthParam : currentMonth(),
  );
  const [incomeText, setIncomeText] = useState("");
  const [strategy, setStrategy] = useState<BudgetStrategy>("envelope");
  const [savingsText, setSavingsText] = useState("");
  const [edited, setEdited] = useState<AllocationRow[] | null>(null);
  const [confirmOver, setConfirmOver] = useState(false);
  const [busy, setBusy] = useState<BudgetStatus | "copy" | null>(null);
  const [error, setError] = useState<SaveError | null>(null);
  const jars = useApiData<BudgetJarList>("/budgets/jars");

  const income = parseBudgetAmount(incomeText);
  const savings = parseBudgetAmount(savingsText);
  const setupReady =
    MONTH_PATTERN.test(month) &&
    income !== null &&
    (strategy !== "pyf" || savings !== null);
  const editedInputs = edited ? toAllocationInputs(edited) : null;

  let request: BudgetPreviewRequest | null = null;
  if (setupReady && (!edited || editedInputs)) {
    request = {
      period_month: monthToPeriod(month),
      strategy,
      expected_income: income,
      savings_target: strategy === "pyf" ? savings : null,
      ...(editedInputs ? { allocations: editedInputs } : {}),
    };
  }
  const preview = useBudgetPreview(request);
  const shown = preview.fresh ?? (preview.loading ? preview.data : undefined);
  const rows = edited ?? (shown ? toRows(shown.budget.allocations) : null);
  const warnings = preview.fresh?.warnings ?? [];
  const overIncome = warnings.some((w) => w.code === "planned_exceeds_income");
  const budgetExists = warnings.some((w) => w.code === "budget_exists");
  const canSave =
    !!rows &&
    !!preview.fresh &&
    !!toAllocationInputs(rows) &&
    (!overIncome || confirmOver) &&
    busy === null;

  /** Đổi thiết lập → bỏ phần đã chỉnh, để backend tính lại phân bổ gợi ý. */
  function resetAllocations() {
    setEdited(null);
    setConfirmOver(false);
    setError(null);
  }

  function changeAmount(index: number, text: string) {
    if (!rows || (!edited && preview.loading)) return;
    setEdited(rows.map((r, i) => (i === index ? { ...r, amountText: text } : r)));
    setError(null);
  }

  async function save(status: BudgetStatus) {
    const allocations = rows ? toAllocationInputs(rows) : null;
    if (!allocations || income === null) return;
    const body: BudgetCreate = {
      period_month: monthToPeriod(month),
      strategy,
      expected_income: income,
      status,
      allocations,
      confirm_over_income: confirmOver,
    };
    setBusy(status);
    setError(null);
    try {
      await apiRequest<Budget>("POST", "/budgets", body);
      router.push(`/budget?month=${month}`);
    } catch (err) {
      setError({
        message: describeError(err),
        budgetExists: err instanceof ApiError && err.status === 409,
      });
      setBusy(null);
    }
  }

  async function copyPrevious() {
    const body: BudgetCopyRequest = { to_month: monthToPeriod(month) };
    setBusy("copy");
    setError(null);
    try {
      await apiRequest<Budget>("POST", "/budgets/copy-from-previous", body);
      router.push(`/budget?month=${month}`);
    } catch (err) {
      setError({
        message: describeError(err),
        budgetExists: err instanceof ApiError && err.status === 409,
      });
      setBusy(null);
    }
  }

  const openExisting = (
    <Link
      href={`/budget?month=${month}`}
      className="underline underline-offset-3"
    >
      Mở ngân sách {formatMonthLabel(month).toLowerCase()}
    </Link>
  );

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. Thiết lập</CardTitle>
          <CardDescription>
            Chọn tháng, thu nhập dự kiến và cách bạn muốn chia tiền. Đổi thu
            nhập hoặc chiến lược sẽ tính lại phân bổ gợi ý.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="budget-month">Tháng</Label>
              <Input
                id="budget-month"
                type="month"
                value={month}
                onChange={(e) => {
                  if (e.target.value) setMonth(e.target.value);
                  setError(null);
                }}
              />
              <span className="text-xs text-muted-foreground">
                {MONTH_PATTERN.test(month) ? formatMonthLabel(month) : ""}
              </span>
            </div>
            <AmountField
              id="budget-income"
              label="Thu nhập dự kiến"
              placeholder="25.000.000"
              value={incomeText}
              onChange={(v) => {
                setIncomeText(v);
                resetAllocations();
              }}
            />
          </div>

          <div
            role="radiogroup"
            aria-label="Chiến lược ngân sách"
            className="grid gap-3 md:grid-cols-3"
          >
            {STRATEGIES.map((s) => (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={strategy === s}
                onClick={() => {
                  setStrategy(s);
                  resetAllocations();
                }}
                className={cn(
                  "flex flex-col gap-1 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted",
                  strategy === s && "border-primary bg-muted ring-1 ring-primary",
                )}
              >
                <span className="font-medium">{STRATEGY_LABELS[s]}</span>
                <span className="text-muted-foreground">
                  {STRATEGY_DESCRIPTIONS[s]}
                </span>
              </button>
            ))}
          </div>

          {strategy === "pyf" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <AmountField
                id="budget-savings"
                label="Tiết kiệm trước (trích ngay khi nhận lương)"
                placeholder="5.000.000"
                value={savingsText}
                onChange={(v) => {
                  setSavingsText(v);
                  resetAllocations();
                }}
              />
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 border-t pt-4 text-sm">
            <span className="text-muted-foreground">
              Hoặc dùng lại ngân sách tháng trước (lưu thành nháp):
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={copyPrevious}
              disabled={busy !== null || !MONTH_PATTERN.test(month)}
            >
              <CopyIcon data-icon="inline-start" />
              {busy === "copy" ? "Đang copy…" : "Copy tháng trước"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="pb-0">
        <CardHeader>
          <CardTitle>2. Phân bổ</CardTitle>
          <CardDescription>
            Sửa số tiền từng dòng nếu muốn — tổng và cảnh báo được tính lại tự
            động.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 px-0">
          {!setupReady && (
            <p className="px-4 pb-4 text-sm text-muted-foreground">
              Nhập thu nhập dự kiến
              {strategy === "pyf" ? " và khoản tiết kiệm trước" : ""} để xem
              phân bổ gợi ý.
            </p>
          )}
          {preview.error && (
            <p role="alert" className="px-4 pb-4 text-sm text-destructive">
              {describeError(preview.error)}
            </p>
          )}
          {setupReady && warnings.length > 0 && (
            <div className="flex flex-col gap-2 px-4">
              <BudgetWarnings warnings={warnings} />
              {budgetExists && <p className="text-sm">{openExisting}</p>}
            </div>
          )}
          {setupReady && rows && (
            <>
              {edited && (
                <div className="px-4">
                  <Button variant="ghost" size="sm" onClick={resetAllocations}>
                    <RotateCcwIcon data-icon="inline-start" />
                    Khôi phục phân bổ gợi ý
                  </Button>
                </div>
              )}
              <AllocationPreviewTable
                rows={rows}
                onAmountChange={changeAmount}
                totals={shown?.budget.totals}
                expectedIncome={income}
                jars={jars.data?.items}
                stale={preview.loading}
              />
            </>
          )}
        </CardContent>
      </Card>

      {setupReady && shown && (
        <Card>
          <CardHeader>
            <CardTitle>So với mốc 50/30/20</CardTitle>
          </CardHeader>
          <CardContent>
            <ReferenceComparison reference={shown.reference_50_30_20} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>3. Lưu</CardTitle>
          <CardDescription>
            Nháp để chỉnh tiếp sau; kích hoạt để dùng làm ngân sách của tháng.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
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
              variant="outline"
              disabled={!canSave}
              onClick={() => save("draft")}
            >
              {busy === "draft" ? "Đang lưu…" : "Lưu nháp"}
            </Button>
            <Button disabled={!canSave} onClick={() => save("active")}>
              {busy === "active" ? "Đang lưu…" : "Lưu & kích hoạt"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error.message} {error.budgetExists && openExisting}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
