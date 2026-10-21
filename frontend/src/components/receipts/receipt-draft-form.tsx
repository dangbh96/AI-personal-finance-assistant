"use client";

import { SparklesIcon } from "lucide-react";
import { useState } from "react";

import {
  TransactionFields,
  validateTransactionValues,
  type TransactionFormValues,
} from "@/components/transactions/transaction-fields";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  apiRequest,
  describeError,
  type Category,
  type ReceiptConfirm,
  type ReceiptConfirmResult,
  type ReceiptDetail,
} from "@/lib/api";
import { formatAmountPlain } from "@/lib/format";

function initialValues(detail: ReceiptDetail): TransactionFormValues {
  const draft = detail.transaction_draft;
  if (draft) {
    return {
      direction: draft.direction,
      categoryId: draft.category_id,
      spendingType: draft.spending_type ?? null,
      amountText: formatAmountPlain(draft.amount),
      occurredOn: draft.occurred_on,
      note: draft.note,
    };
  }
  const prefill = detail.manual_prefill;
  return {
    direction: prefill?.direction ?? "expense",
    categoryId: prefill?.category_id ?? null,
    spendingType: prefill?.spending_type ?? null,
    amountText:
      prefill?.amount !== null && prefill?.amount !== undefined
        ? formatAmountPlain(prefill.amount)
        : "",
    occurredOn: prefill?.occurred_on ?? "",
    note: prefill?.note ?? "",
  };
}

/**
 * Draft giao dịch từ hoá đơn (hoặc form nhập tay điền sẵn khi AI chưa đọc được). User sửa rồi
 * "Lưu giao dịch" → `POST /receipts/{id}/confirm` — chỉ lúc này giao dịch mới được tạo.
 * Cha đặt `key={receipt.id}` để form khởi tạo lại khi đổi hoá đơn.
 */
export function ReceiptDraftForm({
  detail,
  categories,
  onSaved,
}: {
  detail: ReceiptDetail;
  categories: Category[];
  onSaved: (result: ReceiptConfirmResult) => void;
}) {
  const [values, setValues] = useState(() => initialValues(detail));
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const draft = detail.transaction_draft;
  const manual = !draft;
  const { errors } = validateTransactionValues(values);

  async function save() {
    setSubmitted(true);
    const { payload } = validateTransactionValues(values);
    if (!payload) return;
    setSaving(true);
    setError(null);
    try {
      const result = await apiRequest<ReceiptConfirmResult>(
        "POST",
        `/receipts/${detail.receipt.id}/confirm`,
        payload satisfies ReceiptConfirm,
      );
      onSaved(result);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      aria-label={manual ? "Nhập thủ công từ hoá đơn" : "Draft giao dịch"}
      className="flex flex-col gap-4 rounded-lg border p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            {manual ? "Nhập thủ công từ ảnh này" : "Draft giao dịch"}
          </p>
          <p className="text-xs text-muted-foreground">
            {manual
              ? "Đã điền sẵn phần AI đoán được — bạn kiểm tra và bổ sung giúp nhé."
              : "Bạn kiểm tra / sửa trước khi lưu. Chưa có gì được ghi cho tới khi bấm Lưu."}
          </p>
          {draft?.reason && (
            <p className="mt-1 text-xs text-muted-foreground">💡 {draft.reason}</p>
          )}
        </div>
        {draft?.matched_preference_id && (
          <Badge
            variant="outline"
            className="border-violet-300 text-violet-700 dark:border-violet-800 dark:text-violet-300"
          >
            <SparklesIcon data-icon="inline-start" />
            Theo sở thích đã học
          </Badge>
        )}
      </div>

      <fieldset disabled={saving} className="contents">
        <TransactionFields
          idPrefix={`receipt-${detail.receipt.id}`}
          values={values}
          onChange={setValues}
          categories={categories}
          errors={submitted ? errors : undefined}
          className="grid gap-3 sm:grid-cols-2"
        />
      </fieldset>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <Button onClick={save} disabled={saving}>
          {saving ? "Đang lưu…" : "Lưu giao dịch"}
        </Button>
      </div>
    </section>
  );
}
