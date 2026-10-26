"use client";

import { useMemo, useState } from "react";

import { FlagTransactionPicker } from "@/components/reviews/flag-transaction-picker";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  withQuery,
  type ReflectionAnswer,
  type ReflectionCreate,
  type TransactionList,
} from "@/lib/api";
import { formatVND } from "@/lib/format";

const MAX_ANSWER_LENGTH = 2000;

type ReviewKind = ReflectionAnswer["review_kind"];

const COPY: Record<
  ReviewKind,
  { pickerTitle: string; flaggedPrefix: string; placeholder: string; empty: string }
> = {
  weekly: {
    pickerTitle: "Khoản nào không đáng tiền?",
    flaggedPrefix: "Không đáng tiền",
    placeholder: "Ví dụ: Có, 2 lần đặt đồ ăn lúc muộn.",
    empty: "Tuần này chưa có khoản chi nào.",
  },
  monthly: {
    pickerTitle: "Khoản nào bạn muốn nhìn lại?",
    flaggedPrefix: "Khoản đã chọn",
    placeholder: "Ví dụ: Giữ mức ăn uống; laptop là khoản một lần.",
    empty: "Tháng này chưa có khoản chi nào.",
  },
};

/** Câu hỏi gợi ý nhìn lại và chọn khoản chi trong kỳ; lưu xong review thành `completed`. */
export function ReflectionForm({
  kind,
  reviewId,
  question,
  reflections,
  from,
  to,
  markedIds,
  markLabel,
  onSaved,
}: {
  kind: ReviewKind;
  reviewId: string;
  question: string;
  reflections: ReflectionAnswer[];
  /** Kỳ của review (YYYY-MM-DD) — danh sách khoản chi để tick. */
  from: string;
  to: string;
  /** Giao dịch được gắn nhãn `markLabel` (vd "Lặp lại", "Bất thường"). */
  markedIds: ReadonlySet<string>;
  markLabel: string;
  onSaved: (answer: ReflectionAnswer) => void;
}) {
  const copy = COPY[kind];
  const transactions = useApiData<TransactionList>(
    withQuery("/transactions", { from, to, direction: "expense", page_size: 200 }),
  );
  const [answer, setAnswer] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const items = useMemo(() => transactions.data?.items ?? [], [transactions.data]);
  const byId = useMemo(() => new Map(items.map((t) => [t.id, t])), [items]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      const body: ReflectionCreate = {
        answer,
        flagged_transaction_ids: [...selected],
      };
      const saved = await apiRequest<ReflectionAnswer>(
        "POST",
        `/reviews/${kind}/${reviewId}/reflections`,
        body,
      );
      setAnswer("");
      setSelected(new Set());
      setSavedMessage("Đã lưu chia sẻ của bạn.");
      onSaved(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const empty = !answer.trim() && selected.size === 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Nhìn lại</CardTitle>
        <CardDescription>{question}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {reflections.length > 0 && (
          <ul className="flex flex-col gap-2">
            {reflections.map((r) => (
              <li key={r.id} className="rounded-lg bg-muted/60 px-3 py-2 text-sm">
                {r.answer && <p>“{r.answer}”</p>}
                {r.flagged_transaction_ids.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {copy.flaggedPrefix}:{" "}
                    {r.flagged_transaction_ids
                      .map((id) => {
                        const t = byId.get(id);
                        return t
                          ? `${t.note ?? t.category.name} (${formatVND(t.amount)})`
                          : "giao dịch đã xoá";
                      })
                      .join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`reflection-answer-${kind}`}>Chia sẻ của bạn</Label>
            <textarea
              id={`reflection-answer-${kind}`}
              value={answer}
              maxLength={MAX_ANSWER_LENGTH}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder={copy.placeholder}
              className="min-h-20 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">
              {copy.pickerTitle}{" "}
              <span className="font-normal text-muted-foreground">
                (tuỳ chọn{selected.size > 0 ? ` · đã chọn ${selected.size}` : ""})
              </span>
            </span>
            {transactions.error && !transactions.data ? (
              <p role="alert" className="text-sm text-destructive">
                {describeError(transactions.error)}
              </p>
            ) : transactions.loading && !transactions.data ? (
              <p className="text-sm text-muted-foreground">Đang tải giao dịch…</p>
            ) : (
              <FlagTransactionPicker
                transactions={items}
                selected={selected}
                onToggle={toggle}
                markedIds={markedIds}
                markLabel={markLabel}
                checkboxLabel={copy.flaggedPrefix}
                emptyText={copy.empty}
                disabled={saving}
              />
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {savedMessage && (
            <p role="status" className="text-sm text-emerald-700 dark:text-emerald-300">
              {savedMessage}
            </p>
          )}
          <div>
            <Button type="submit" disabled={saving || empty}>
              {saving ? "Đang lưu…" : "Lưu chia sẻ"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
