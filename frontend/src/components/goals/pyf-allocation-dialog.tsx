"use client";

import { CheckCircle2Icon, PiggyBankIcon, TriangleAlertIcon } from "lucide-react";
import Link from "next/link";
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
import { usePyfProposal } from "@/hooks/use-pyf-proposal";
import {
  apiRequest,
  describeError,
  withQuery,
  type PyfAllocationRequest,
  type PyfAllocationResult,
  type PyfProposal,
  type PyfProposalRequest,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import {
  formatAmountPlain,
  formatDate,
  formatMonthLabel,
  formatVND,
} from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Dialog "Nhận lương" (Pay Yourself First): thu nhập đã lưu → đề xuất trích cho mục tiêu theo
 * ưu tiên + tiết kiệm ngân sách → user chỉnh → xác nhận (`POST /goals/allocations`).
 * Đóng dialog mà chưa xác nhận: thu nhập vẫn còn, không tạo khoản góp nào.
 */
export function PyfAllocationDialog({
  proposal,
  today,
  onOpenChange,
  onConfirmed,
}: {
  /** `null` = đóng. */
  proposal: PyfProposal | null;
  today?: string | null;
  onOpenChange: (open: boolean) => void;
  onConfirmed?: (result: PyfAllocationResult) => void;
}) {
  return (
    <Dialog open={proposal !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PiggyBankIcon className="size-4 text-emerald-600" aria-hidden />
            Nhận lương — trả cho mình trước
          </DialogTitle>
          <DialogDescription>
            Trích tiền cho mục tiêu và tiết kiệm trước, phần còn lại mới dành để chi tiêu. Bạn có
            thể chỉnh từng số trước khi xác nhận.
          </DialogDescription>
        </DialogHeader>
        {proposal && (
          <PyfAllocationForm
            key={proposal.income_transaction_id}
            proposal={proposal}
            today={today ?? null}
            onClose={() => onOpenChange(false)}
            onConfirmed={onConfirmed}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

type Draft = { amounts: Record<string, string>; savings: string };

function initialDraft(proposal: PyfProposal): Draft {
  return {
    amounts: Object.fromEntries(
      proposal.items.map((i) => [i.goal_id, formatAmountPlain(i.amount)]),
    ),
    savings: formatAmountPlain(proposal.budget_savings_amount),
  };
}

/** "" / "0" → 0; số hợp lệ → số; không hiểu → null. */
function parseAllocation(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "" || /^0+$/.test(trimmed)) return 0;
  return parseAmountInput(trimmed);
}

function PyfAllocationForm({
  proposal,
  today,
  onClose,
  onConfirmed,
}: {
  proposal: PyfProposal;
  today: string | null;
  onClose: () => void;
  onConfirmed?: (result: PyfAllocationResult) => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => initialDraft(proposal));
  const [edited, setEdited] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PyfAllocationResult | null>(null);

  const hasSavings = proposal.budget_savings_target !== null;
  const parsedItems = proposal.items.map((i) => ({
    goal_id: i.goal_id,
    amount: parseAllocation(draft.amounts[i.goal_id] ?? ""),
  }));
  const parsedSavings = hasSavings ? parseAllocation(draft.savings) : 0;
  const invalid =
    parsedItems.some((i) => i.amount === null) || parsedSavings === null;
  const items = parsedItems.map((i) => ({ goal_id: i.goal_id, amount: i.amount ?? 0 }));
  const savings = parsedSavings ?? 0;

  const request: PyfProposalRequest | null =
    edited && !invalid
      ? {
          income_transaction_id: proposal.income_transaction_id,
          items,
          budget_savings_amount: savings,
        }
      : null;
  const preview = usePyfProposal(request, today);
  const view = (edited ? preview.data : null) ?? proposal;
  const stale = edited && (preview.loading || invalid);

  function setAmount(goalId: string, text: string) {
    setEdited(true);
    setDraft((d) => ({ ...d, amounts: { ...d.amounts, [goalId]: text } }));
  }

  async function confirm() {
    if (invalid) return;
    setSaving(true);
    setError(null);
    try {
      const body: PyfAllocationRequest = {
        income_transaction_id: proposal.income_transaction_id,
        items: items.filter((i) => i.amount > 0),
        budget_savings_amount: savings,
      };
      const saved = await apiRequest<PyfAllocationResult>(
        "POST",
        withQuery("/goals/allocations", { today }),
        body,
      );
      setResult(saved);
      onConfirmed?.(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const income = proposal.income;

  if (result) {
    return (
      <div className="flex flex-col gap-4">
        <div
          role="status"
          className="flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
        >
          <CheckCircle2Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div className="flex flex-col gap-1">
            <p className="font-medium">
              {result.contributions.length > 0
                ? `Đã ghi ${result.contributions.length} khoản góp (${formatVND(result.goal_total)}) cho mục tiêu.`
                : "Không ghi khoản góp nào cho mục tiêu."}
            </p>
            {result.budget_savings_amount > 0 && (
              <p>Tiết kiệm ngân sách: {formatVND(result.budget_savings_amount)}.</p>
            )}
            <p>
              Còn lại để chi tiêu:{" "}
              <strong>{formatVND(result.available_spending)}</strong>
            </p>
          </div>
        </div>
        <DialogFooter>
          <Link
            href="/goals"
            className="inline-flex items-center text-sm underline underline-offset-3"
          >
            Xem mục tiêu
          </Link>
          <Button onClick={onClose}>Đóng</Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <section aria-label="Bước 1: thu nhập đã lưu" className="flex flex-col gap-1">
        <p className="text-xs font-medium text-muted-foreground uppercase">
          1. Thu nhập đã lưu
        </p>
        <p className="flex items-center gap-2">
          <CheckCircle2Icon className="size-4 text-emerald-600" aria-hidden />
          <span>
            {income.note || income.category_name} ·{" "}
            <strong>{formatVND(income.amount)}</strong> · {formatDate(income.occurred_on)}
          </span>
        </p>
      </section>

      <section aria-label="Bước 2: mục tiêu" className="flex flex-col gap-2">
        <p className="text-xs font-medium text-muted-foreground uppercase">
          2. Trích cho mục tiêu (theo ưu tiên)
        </p>
        {view.items.length === 0 ? (
          <p className="text-muted-foreground">
            Chưa có mục tiêu đang thực hiện.{" "}
            <Link href="/goals" className="underline underline-offset-3">
              Tạo mục tiêu
            </Link>
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b text-left">
                  <th className="py-2 pr-2 font-medium">Mục tiêu</th>
                  <th className="py-2 pr-2 text-right font-medium">Gợi ý / tháng</th>
                  <th className="py-2 pr-2 text-right font-medium">Phân bổ</th>
                  <th className="py-2 text-right font-medium">Còn thiếu sau</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((item) => (
                  <tr key={item.goal_id} className="border-b last:border-0">
                    <td className="py-2 pr-2 align-top">
                      <p className="font-medium">
                        {item.priority}. {item.name}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Còn thiếu {formatVND(item.remaining_amount)} · hạn{" "}
                        {formatDate(item.deadline)}
                      </p>
                    </td>
                    <td className="py-2 pr-2 text-right align-top tabular-nums">
                      {formatVND(item.suggested_monthly_saving)}
                    </td>
                    <td className="py-2 pr-2 text-right align-top">
                      <Input
                        aria-label={`Số tiền cho ${item.name}`}
                        inputMode="numeric"
                        className={cn(
                          "ml-auto w-32 text-right tabular-nums",
                          item.exceeds_remaining && "border-destructive",
                        )}
                        value={draft.amounts[item.goal_id] ?? ""}
                        onChange={(e) => setAmount(item.goal_id, e.target.value)}
                        disabled={saving}
                      />
                    </td>
                    <td
                      className={cn(
                        "py-2 text-right align-top tabular-nums",
                        stale && "opacity-50",
                        item.remaining_after < 0 && "text-destructive",
                      )}
                    >
                      {formatVND(item.remaining_after)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {hasSavings && (
        <section aria-label="Bước 3: tiết kiệm ngân sách" className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted-foreground uppercase">
            3. Tiết kiệm ngân sách{" "}
            {formatMonthLabel(proposal.budget_month.slice(0, 7)).toLowerCase()}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground">
              Khoản tiết kiệm chưa gắn mục tiêu · kế hoạch{" "}
              {formatVND(proposal.budget_savings_target ?? 0)}. Đặt 0 nếu không muốn trích.
            </p>
            <Input
              aria-label="Số tiền tiết kiệm ngân sách"
              inputMode="numeric"
              className="w-32 text-right tabular-nums"
              value={draft.savings}
              onChange={(e) => {
                setEdited(true);
                setDraft((d) => ({ ...d, savings: e.target.value }));
              }}
              disabled={saving}
            />
          </div>
        </section>
      )}

      <section
        aria-label="Còn lại để chi tiêu"
        className={cn(
          "flex flex-col gap-2 rounded-lg bg-muted/50 p-3",
          stale && "opacity-60",
        )}
      >
        <p className="text-xs font-medium text-muted-foreground uppercase">
          {hasSavings ? "4" : "3"}. Còn lại để chi tiêu
        </p>
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 tabular-nums">
          <dt>Thu nhập</dt>
          <dd className="text-right">{formatVND(view.income_amount)}</dd>
          <dt>Cho mục tiêu</dt>
          <dd className="text-right">−{formatVND(view.goal_total)}</dd>
          {hasSavings && (
            <>
              <dt>Tiết kiệm ngân sách</dt>
              <dd className="text-right">−{formatVND(view.budget_savings_amount)}</dd>
            </>
          )}
          <dt className="font-medium">Có thể chi tiêu</dt>
          <dd
            className={cn(
              "text-right text-base font-semibold",
              view.available_spending < 0 && "text-destructive",
            )}
          >
            {formatVND(view.available_spending)}
          </dd>
        </dl>
      </section>

      {invalid && (
        <p role="alert" className="text-sm text-destructive">
          Có số tiền chưa hợp lệ — nhập số nguyên đồng (vd 4400000, 4tr4).
        </p>
      )}
      {!stale && view.warnings.length > 0 && (
        <div
          role="status"
          className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          <ul className="flex flex-col gap-1">
            {view.warnings.map((w) => (
              <li key={`${w.code}-${w.message}`}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}
      {(error || preview.error) && (
        <p role="alert" className="text-sm text-destructive">
          {error ?? describeError(preview.error)}
        </p>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={saving}>
          Để sau
        </Button>
        <Button
          onClick={confirm}
          disabled={saving || invalid || stale || !view.valid || !!preview.error}
        >
          {saving ? "Đang lưu…" : "Xác nhận phân bổ"}
        </Button>
      </DialogFooter>
    </div>
  );
}
