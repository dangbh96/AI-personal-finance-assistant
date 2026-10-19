"use client";

import { CheckIcon, SparklesIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
  type Preference,
  type TransactionCreate,
  type TransactionCreateResult,
  type TransactionDraft,
  type TransactionParseResponse,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Dưới ngưỡng này UI nhắc user kiểm tra kỹ draft. */
const LOW_CONFIDENCE = 0.6;

type DraftStatus = "pending" | "saving" | "saved" | "skipped";

type DraftItem = {
  key: string;
  draft: TransactionDraft;
  values: TransactionFormValues;
  status: DraftStatus;
  submitted: boolean;
  error: string | null;
  /** Preference backend vừa học khi user sửa đề xuất của AI rồi lưu. */
  learned: Preference | null;
};

function toValues(draft: TransactionDraft): TransactionFormValues {
  return {
    direction: draft.direction,
    categoryId: draft.category_id,
    spendingType: draft.spending_type ?? null,
    amountText: draft.amount.toLocaleString("vi-VN"),
    occurredOn: draft.occurred_on,
    note: draft.note,
  };
}

/**
 * Draft do AI tạo: user sửa rồi lưu từng cái hoặc "Lưu tất cả". Draft lỗi không chặn draft khác.
 * Gọi `onDone(savedCount, learned)` khi mọi draft đã được lưu hoặc bỏ qua; `learned` là các
 * preference backend vừa học từ những draft user đã sửa phân loại.
 */
export function TransactionDraftReview({
  result,
  categories,
  onDone,
}: {
  result: TransactionParseResponse;
  categories: Category[];
  onDone: (savedCount: number, learned: Preference[]) => void;
}) {
  const [items, setItems] = useState<DraftItem[]>(() =>
    result.drafts.map((draft, i) => ({
      key: String(i),
      draft,
      values: toValues(draft),
      status: "pending",
      submitted: false,
      error: null,
      learned: null,
    })),
  );
  const reported = useRef(false);

  const pending = items.filter((i) => i.status === "pending");
  const saving = items.some((i) => i.status === "saving");
  const finished = items.every(
    (i) => i.status === "saved" || i.status === "skipped",
  );
  const savedCount = items.filter((i) => i.status === "saved").length;

  useEffect(() => {
    if (finished && !reported.current) {
      reported.current = true;
      onDone(
        savedCount,
        items.flatMap((i) => (i.learned ? [i.learned] : [])),
      );
    }
  }, [finished, savedCount, items, onDone]);

  function update(key: string, patch: Partial<DraftItem>) {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, ...patch } : item)),
    );
  }

  async function save(item: DraftItem): Promise<void> {
    const { payload } = validateTransactionValues(item.values);
    if (!payload) {
      update(item.key, { submitted: true });
      return;
    }
    update(item.key, { status: "saving", submitted: true, error: null });
    try {
      const saved = await apiRequest<TransactionCreateResult>(
        "POST",
        "/transactions",
        {
          ...payload,
          source: "nl",
          raw_input: result.raw_input,
          ai_suggestion: { ...item.draft, model: result.model },
        } satisfies TransactionCreate,
      );
      update(item.key, {
        status: "saved",
        learned: saved.learned_preference ?? null,
      });
    } catch (err) {
      update(item.key, { status: "pending", error: describeError(err) });
    }
  }

  async function saveAll() {
    // Tuần tự để giữ đúng thứ tự giao dịch trong câu.
    for (const item of pending) await save(item);
  }

  return (
    <div className="flex flex-col gap-4">
      {result.warnings.length > 0 && (
        <div
          role="status"
          className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          <ul className="flex flex-col gap-1">
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {items.map((item, index) => (
        <DraftCard
          key={item.key}
          item={item}
          label={
            items.length > 1
              ? `Giao dịch ${index + 1}/${items.length}`
              : "Giao dịch"
          }
          categories={categories}
          onChange={(values) => update(item.key, { values })}
          onSave={() => save(item)}
          onSkip={() => update(item.key, { status: "skipped", error: null })}
        />
      ))}

      {pending.length > 1 && (
        <div className="flex justify-end">
          <Button onClick={saveAll} disabled={saving}>
            {saving ? "Đang lưu…" : `Lưu tất cả (${pending.length})`}
          </Button>
        </div>
      )}
    </div>
  );
}

function DraftCard({
  item,
  label,
  categories,
  onChange,
  onSave,
  onSkip,
}: {
  item: DraftItem;
  label: string;
  categories: Category[];
  onChange: (values: TransactionFormValues) => void;
  onSave: () => void;
  onSkip: () => void;
}) {
  const { draft, values, status } = item;

  if (status === "saved" || status === "skipped") {
    const amount = parseAmountInput(values.amountText);
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm",
          status === "skipped" && "text-muted-foreground",
        )}
      >
        {status === "saved" && (
          <CheckIcon className="size-4 text-emerald-600" aria-hidden />
        )}
        <span className="font-medium">
          {status === "saved" ? "Đã lưu" : "Đã bỏ qua"}
        </span>
        <span className="truncate">
          · {values.note || label}
          {amount !== null ? ` · ${formatVND(amount)}` : ""}
        </span>
      </div>
    );
  }

  const { errors } = validateTransactionValues(values);
  const fromPreference = Boolean(draft.matched_preference_id);
  const lowConfidence = !fromPreference && draft.confidence < LOW_CONFIDENCE;

  return (
    <section
      aria-label={label}
      className={cn(
        "flex flex-col gap-4 rounded-lg border p-4",
        lowConfidence && "border-amber-300 dark:border-amber-800",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{label}</p>
          {draft.reason && (
            <p className="text-xs text-muted-foreground">💡 {draft.reason}</p>
          )}
        </div>
        {fromPreference ? (
          <Badge
            variant="outline"
            className="border-violet-300 text-violet-700 dark:border-violet-800 dark:text-violet-300"
          >
            <SparklesIcon data-icon="inline-start" />
            Theo sở thích đã học
          </Badge>
        ) : lowConfidence ? (
          <Badge
            variant="outline"
            className="border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300"
          >
            AI chưa chắc chắn — bạn kiểm tra giúp nhé
          </Badge>
        ) : (
          <Badge variant="outline">
            Độ tin cậy {Math.round(draft.confidence * 100)}%
          </Badge>
        )}
      </div>

      <fieldset disabled={status === "saving"} className="contents">
        <TransactionFields
          idPrefix={`draft-${item.key}`}
          values={values}
          onChange={onChange}
          categories={categories}
          errors={item.submitted ? errors : undefined}
          className="grid gap-3 sm:grid-cols-2"
        />
      </fieldset>

      {item.error && (
        <p role="alert" className="text-sm text-destructive">
          {item.error}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <Button
          variant="ghost"
          onClick={onSkip}
          disabled={status === "saving"}
        >
          Bỏ qua
        </Button>
        <Button onClick={onSave} disabled={status === "saving"}>
          {status === "saving" ? "Đang lưu…" : "Lưu"}
        </Button>
      </div>
    </section>
  );
}
