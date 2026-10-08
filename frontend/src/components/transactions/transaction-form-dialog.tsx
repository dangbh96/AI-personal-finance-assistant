"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  apiRequest,
  describeError,
  type Category,
  type Direction,
  type SpendingType,
  type Transaction,
  type TransactionCreate,
  type TransactionUpdate,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { todayISO } from "@/lib/dates";
import { formatVND } from "@/lib/format";
import { DIRECTION_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  /** `null` = tạo mới. */
  transaction: Transaction | null;
  onSaved: () => void;
};

export function TransactionFormDialog({
  open,
  onOpenChange,
  categories,
  transaction,
  onSaved,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {transaction ? "Sửa giao dịch" : "Thêm giao dịch"}
          </DialogTitle>
          <DialogDescription>
            Ghi lại khoản thu hoặc chi. Số tiền có thể gõ tắt: 55k, 1tr5, 25
            triệu…
          </DialogDescription>
        </DialogHeader>
        {open && (
          <TransactionForm
            key={transaction?.id ?? "new"}
            categories={categories}
            transaction={transaction}
            onCancel={() => onOpenChange(false)}
            onSaved={() => {
              onSaved();
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

const SPENDING_TYPE_ITEMS = SPENDING_TYPE_LABELS as Record<string, string>;

function TransactionForm({
  categories,
  transaction,
  onCancel,
  onSaved,
}: {
  categories: Category[];
  transaction: Transaction | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [direction, setDirection] = useState<Direction>(
    transaction?.direction ?? "expense",
  );
  const [categoryId, setCategoryId] = useState<string | null>(
    transaction?.category_id ?? null,
  );
  const [spendingType, setSpendingType] = useState<SpendingType | null>(
    transaction?.spending_type ?? null,
  );
  const [amountText, setAmountText] = useState(
    transaction ? transaction.amount.toLocaleString("vi-VN") : "",
  );
  const [occurredOn, setOccurredOn] = useState(
    transaction?.occurred_on ?? todayISO(),
  );
  const [note, setNote] = useState(transaction?.note ?? "");
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Danh mục đã ẩn vẫn hiện nếu là danh mục hiện tại của giao dịch đang sửa.
  const options = categories.filter(
    (c) =>
      c.kind === direction &&
      (!c.is_archived || c.id === transaction?.category_id),
  );
  const categoryItems = Object.fromEntries(
    options.map((c) => [c.id, `${c.icon ?? ""} ${c.name}`.trim()]),
  );
  const amount = parseAmountInput(amountText);

  const amountError =
    submitted && amount === null ? "Số tiền phải là số nguyên dương" : null;
  const categoryError =
    submitted && !categoryId ? "Chọn danh mục" : null;
  const dateError = submitted && !occurredOn ? "Chọn ngày" : null;

  function changeDirection(next: Direction) {
    if (next === direction) return;
    setDirection(next);
    setCategoryId(null);
    setSpendingType(null);
  }

  function changeCategory(id: string | null) {
    setCategoryId(id);
    const category = categories.find((c) => c.id === id);
    if (direction === "expense" && category?.default_spending_type) {
      setSpendingType(category.default_spending_type);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (amount === null || !categoryId || !occurredOn) return;

    const payload = {
      direction,
      amount,
      occurred_on: occurredOn,
      category_id: categoryId,
      spending_type: direction === "expense" ? spendingType : null,
      note: note.trim() || null,
    };
    setSubmitting(true);
    try {
      if (transaction) {
        await apiRequest<Transaction>(
          "PATCH",
          `/transactions/${transaction.id}`,
          payload satisfies TransactionUpdate,
        );
      } else {
        await apiRequest<Transaction>(
          "POST",
          "/transactions",
          payload satisfies TransactionCreate,
        );
      }
      onSaved();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <div
        role="radiogroup"
        aria-label="Loại giao dịch"
        className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1"
      >
        {(["expense", "income"] as const).map((d) => (
          <button
            key={d}
            type="button"
            role="radio"
            aria-checked={direction === d}
            onClick={() => changeDirection(d)}
            className={cn(
              "h-7 rounded-md text-sm font-medium transition-colors",
              direction === d
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground",
              direction === d && d === "income" && "text-emerald-600",
              direction === d && d === "expense" && "text-rose-600",
            )}
          >
            {DIRECTION_LABELS[d]}
          </button>
        ))}
      </div>

      <Field label="Danh mục" htmlFor="tx-category" error={categoryError}>
        <Select
          items={categoryItems}
          value={categoryId}
          onValueChange={(v) => changeCategory(v as string | null)}
        >
          <SelectTrigger
            id="tx-category"
            className="w-full"
            aria-invalid={!!categoryError}
          >
            <SelectValue placeholder="Chọn danh mục" />
          </SelectTrigger>
          <SelectContent>
            {options.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {categoryItems[c.id]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      {direction === "expense" && (
        <Field label="Loại chi tiêu" htmlFor="tx-spending-type">
          <Select
            items={SPENDING_TYPE_ITEMS}
            value={spendingType}
            onValueChange={(v) => setSpendingType(v as SpendingType | null)}
          >
            <SelectTrigger id="tx-spending-type" className="w-full">
              <SelectValue placeholder="Theo mặc định của danh mục" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SPENDING_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}

      <Field
        label="Số tiền"
        htmlFor="tx-amount"
        error={amountError}
        hint={
          amount !== null ? `= ${formatVND(amount)}` : "Ví dụ: 55k, 1tr5, 250.000"
        }
      >
        <Input
          id="tx-amount"
          inputMode="decimal"
          autoComplete="off"
          placeholder="55k"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          aria-invalid={!!amountError}
        />
      </Field>

      <Field label="Ngày" htmlFor="tx-date" error={dateError}>
        <Input
          id="tx-date"
          type="date"
          value={occurredOn}
          onChange={(e) => setOccurredOn(e.target.value)}
          aria-invalid={!!dateError}
        />
      </Field>

      <Field label="Ghi chú" htmlFor="tx-note">
        <Input
          id="tx-note"
          maxLength={500}
          placeholder="Ăn phở"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Huỷ
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Đang lưu…" : transaction ? "Lưu thay đổi" : "Thêm"}
        </Button>
      </DialogFooter>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
