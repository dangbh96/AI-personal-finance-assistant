"use client";

import { useState } from "react";

import {
  TransactionFields,
  validateTransactionValues,
  type TransactionFormValues,
} from "@/components/transactions/transaction-fields";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  apiRequest,
  describeError,
  type Category,
  type Transaction,
  type TransactionCreate,
  type TransactionUpdate,
} from "@/lib/api";
import { todayISO } from "@/lib/dates";

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

function initialValues(transaction: Transaction | null): TransactionFormValues {
  return {
    direction: transaction?.direction ?? "expense",
    categoryId: transaction?.category_id ?? null,
    spendingType: transaction?.spending_type ?? null,
    amountText: transaction ? transaction.amount.toLocaleString("vi-VN") : "",
    occurredOn: transaction?.occurred_on ?? todayISO(),
    note: transaction?.note ?? "",
  };
}

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
  const [values, setValues] = useState(() => initialValues(transaction));
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { payload, errors } = validateTransactionValues(values);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!payload) return;

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
      <TransactionFields
        idPrefix="tx"
        values={values}
        onChange={setValues}
        categories={categories}
        errors={submitted ? errors : undefined}
        keepCategoryId={transaction?.category_id}
      />

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
