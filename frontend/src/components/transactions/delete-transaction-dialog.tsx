"use client";

import { useState } from "react";

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
import { apiRequest, describeError, type Transaction } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";

export function DeleteTransactionDialog({
  transaction,
  onOpenChange,
  onDeleted,
}: {
  transaction: Transaction | null;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (!transaction) return;
    setDeleting(true);
    setError(null);
    try {
      await apiRequest<void>("DELETE", `/transactions/${transaction.id}`);
      onDeleted();
      onOpenChange(false);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AlertDialog
      open={transaction !== null}
      onOpenChange={(open) => {
        if (!open) setError(null);
        onOpenChange(open);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Xoá giao dịch này?</AlertDialogTitle>
          <AlertDialogDescription>
            {transaction &&
              `${transaction.note ?? transaction.category.name} — ${formatVND(
                transaction.amount,
              )} ngày ${formatDate(transaction.occurred_on)}. `}
            Thao tác này không hoàn tác được.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Huỷ</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? "Đang xoá…" : "Xoá"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
