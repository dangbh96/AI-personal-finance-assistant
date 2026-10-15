"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  Category,
  Direction,
  SpendingType,
  TransactionCreate,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatVND } from "@/lib/format";
import { DIRECTION_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

/** Giá trị đang nhập của một giao dịch (dùng cho form tạo/sửa và draft AI). */
export type TransactionFormValues = {
  direction: Direction;
  categoryId: string | null;
  spendingType: SpendingType | null;
  amountText: string;
  occurredOn: string;
  note: string;
};

export type TransactionFormErrors = {
  amount?: string;
  category?: string;
  occurredOn?: string;
};

export type TransactionPayload = Pick<
  TransactionCreate,
  | "direction"
  | "amount"
  | "occurred_on"
  | "category_id"
  | "spending_type"
  | "note"
>;

export function validateTransactionValues(values: TransactionFormValues): {
  payload: TransactionPayload | null;
  errors: TransactionFormErrors;
} {
  const amount = parseAmountInput(values.amountText);
  const errors: TransactionFormErrors = {};
  if (amount === null) errors.amount = "Số tiền phải là số nguyên dương";
  if (!values.categoryId) errors.category = "Chọn danh mục";
  if (!values.occurredOn) errors.occurredOn = "Chọn ngày";
  if (amount === null || !values.categoryId || !values.occurredOn) {
    return { payload: null, errors };
  }
  return {
    payload: {
      direction: values.direction,
      amount,
      occurred_on: values.occurredOn,
      category_id: values.categoryId,
      spending_type:
        values.direction === "expense" ? values.spendingType : null,
      note: values.note.trim() || null,
    },
    errors,
  };
}

const SPENDING_TYPE_ITEMS = SPENDING_TYPE_LABELS as Record<string, string>;

/**
 * Các ô nhập của một giao dịch: Thu/Chi → danh mục (lọc theo kind) → loại chi tiêu
 * (ẩn khi Thu, tự điền default của danh mục) → số tiền (gõ tắt) → ngày → ghi chú.
 */
export function TransactionFields({
  idPrefix,
  values,
  onChange,
  categories,
  errors = {},
  keepCategoryId,
  className,
}: {
  /** Tiền tố id cho các ô, phải duy nhất trên trang. */
  idPrefix: string;
  values: TransactionFormValues;
  onChange: (values: TransactionFormValues) => void;
  categories: Category[];
  errors?: TransactionFormErrors;
  /** Danh mục đã ẩn vẫn được hiện nếu là danh mục hiện tại của giao dịch đang sửa. */
  keepCategoryId?: string | null;
  /** Thay layout mặc định (cột dọc), vd. lưới 2 cột cho draft. */
  className?: string;
}) {
  const { direction } = values;
  const options = categories.filter(
    (c) =>
      c.kind === direction && (!c.is_archived || c.id === keepCategoryId),
  );
  const categoryItems = Object.fromEntries(
    options.map((c) => [c.id, `${c.icon ?? ""} ${c.name}`.trim()]),
  );
  const amount = parseAmountInput(values.amountText);

  function changeDirection(next: Direction) {
    if (next === direction) return;
    onChange({
      ...values,
      direction: next,
      categoryId: null,
      spendingType: null,
    });
  }

  function changeCategory(id: string | null) {
    const category = categories.find((c) => c.id === id);
    onChange({
      ...values,
      categoryId: id,
      spendingType:
        direction === "expense" && category?.default_spending_type
          ? category.default_spending_type
          : values.spendingType,
    });
  }

  return (
    <div className={className ?? "flex flex-col gap-4"}>
      <div
        role="radiogroup"
        aria-label="Loại giao dịch"
        className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 sm:col-span-2"
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

      <Field
        label="Danh mục"
        htmlFor={`${idPrefix}-category`}
        error={errors.category}
      >
        <Select
          items={categoryItems}
          value={values.categoryId}
          onValueChange={(v) => changeCategory(v as string | null)}
        >
          <SelectTrigger
            id={`${idPrefix}-category`}
            className="w-full"
            aria-invalid={!!errors.category}
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
        <Field label="Loại chi tiêu" htmlFor={`${idPrefix}-spending-type`}>
          <Select
            items={SPENDING_TYPE_ITEMS}
            value={values.spendingType}
            onValueChange={(v) =>
              onChange({ ...values, spendingType: v as SpendingType | null })
            }
          >
            <SelectTrigger id={`${idPrefix}-spending-type`} className="w-full">
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
        htmlFor={`${idPrefix}-amount`}
        error={errors.amount}
        hint={
          amount !== null
            ? `= ${formatVND(amount)}`
            : "Ví dụ: 55k, 1tr5, 250.000"
        }
      >
        <Input
          id={`${idPrefix}-amount`}
          inputMode="decimal"
          autoComplete="off"
          placeholder="55k"
          value={values.amountText}
          onChange={(e) => onChange({ ...values, amountText: e.target.value })}
          aria-invalid={!!errors.amount}
        />
      </Field>

      <Field label="Ngày" htmlFor={`${idPrefix}-date`} error={errors.occurredOn}>
        <Input
          id={`${idPrefix}-date`}
          type="date"
          value={values.occurredOn}
          onChange={(e) => onChange({ ...values, occurredOn: e.target.value })}
          aria-invalid={!!errors.occurredOn}
        />
      </Field>

      <Field
        label="Ghi chú"
        htmlFor={`${idPrefix}-note`}
        className={direction === "expense" ? "sm:col-span-2" : undefined}
      >
        <Input
          id={`${idPrefix}-note`}
          maxLength={500}
          placeholder="Ăn phở"
          value={values.note}
          onChange={(e) => onChange({ ...values, note: e.target.value })}
        />
      </Field>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
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
