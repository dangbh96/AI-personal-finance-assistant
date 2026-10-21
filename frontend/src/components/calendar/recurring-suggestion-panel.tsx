"use client";

import { SparklesIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  apiRequest,
  describeError,
  withQuery,
  type RecurringDetectRequest,
  type RecurringSuggestion,
  type RecurringSuggestionConfirm,
  type RecurringSuggestionList,
  type RecurringTransaction,
} from "@/lib/api";
import { describeSchedule, formatDayMonth } from "@/lib/calendar";
import { formatDate, formatPercent, formatVND } from "@/lib/format";

/**
 * Phát hiện khoản định kỳ từ lịch sử (deterministic, không AI): chỉ là đề xuất — user xác nhận
 * mới tạo khoản định kỳ, từ chối thì lần sau không đề xuất lại.
 */
export function RecurringSuggestionPanel({
  data,
  today,
  onChanged,
}: {
  data: RecurringSuggestionList | undefined;
  today: string;
  onChanged: () => void;
}) {
  const [result, setResult] = useState<RecurringSuggestionList | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const list = result ?? data;
  const suggestions = list?.suggestions ?? [];

  async function detect() {
    setDetecting(true);
    setError(null);
    setMessage(null);
    try {
      const found = await apiRequest<RecurringSuggestionList>(
        "POST",
        withQuery("/recurring-transactions/detect", { today }),
        {} satisfies RecurringDetectRequest,
      );
      setResult(found);
      setMessage(
        found.suggestions.length
          ? `Tìm thấy ${found.suggestions.length} khoản có vẻ định kỳ.`
          : "Không tìm thấy khoản định kỳ mới trong lịch sử.",
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setDetecting(false);
    }
  }

  function drop(id: string) {
    const base = result ?? data;
    if (base) setResult({ ...base, suggestions: base.suggestions.filter((s) => s.id !== id) });
  }

  async function confirm(s: RecurringSuggestion) {
    setBusyId(s.id);
    setError(null);
    setMessage(null);
    try {
      const created = await apiRequest<RecurringTransaction>(
        "POST",
        withQuery(`/recurring-transactions/suggestions/${s.id}/confirm`, { today }),
        {} satisfies RecurringSuggestionConfirm,
      );
      drop(s.id);
      setMessage(
        `Đã thêm “${created.name}” — kỳ tới ${formatDate(created.next_due_on)}.`,
      );
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusyId(null);
    }
  }

  async function dismiss(s: RecurringSuggestion) {
    setBusyId(s.id);
    setError(null);
    setMessage(null);
    try {
      await apiRequest<void>("POST", `/recurring-transactions/suggestions/${s.id}/dismiss`);
      drop(s.id);
      setMessage(`Đã bỏ qua “${s.name}”.`);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SparklesIcon className="size-4" aria-hidden />
          Phát hiện khoản định kỳ
        </CardTitle>
        <CardDescription>
          Tìm các khoản cùng danh mục, số tiền gần như nhau (±10%), lặp lại hằng tuần / hằng tháng
          ít nhất 3 lần trong 6 tháng gần đây.
        </CardDescription>
        <CardAction>
          <Button size="sm" variant="outline" onClick={detect} disabled={detecting}>
            {detecting ? "Đang tìm…" : "Phát hiện từ lịch sử"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {message && (
          <p role="status" className="text-sm text-muted-foreground">
            {message}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {suggestions.length > 0 && (
          <ul className="flex flex-col gap-2">
            {suggestions.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div className="flex min-w-0 items-start gap-2">
                  <span className="text-xl" aria-hidden>
                    {s.icon}
                  </span>
                  <div className="min-w-0 text-sm">
                    <p className="font-medium">
                      {s.name} ·{" "}
                      <span className="tabular-nums">
                        {s.direction === "income" ? "+" : "−"}
                        {formatVND(s.amount)}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.category_name} · {describeSchedule(s)} · kỳ tới{" "}
                      {formatDate(s.next_due_on)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {s.occurrences} lần ({s.amounts.map((a) => formatVND(a)).join(", ")}) từ{" "}
                      {formatDayMonth(s.first_occurred_on)} tới {formatDate(s.last_occurred_on)} ·
                      độ tin cậy {formatPercent(Math.round(s.confidence * 100))}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => confirm(s)} disabled={busyId !== null}>
                    {busyId === s.id ? "Đang lưu…" : "Xác nhận"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => dismiss(s)}
                    disabled={busyId !== null}
                  >
                    Bỏ qua
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {list && suggestions.length === 0 && !message && (
          <p className="text-sm text-muted-foreground">
            Chưa có đề xuất. Bấm “Phát hiện từ lịch sử” để tìm lương, tiền nhà, hoá đơn lặp lại.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
