"use client";

import { SpendingTypeBadge } from "@/components/spending-type-badge";
import { Badge } from "@/components/ui/badge";
import type { Transaction } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Danh sách khoản chi trong kỳ để tick (tuần: "không đáng tiền"; tháng: khoản muốn nhìn lại). */
export function FlagTransactionPicker({
  transactions,
  selected,
  onToggle,
  markedIds,
  markLabel,
  checkboxLabel = "Không đáng tiền",
  emptyText = "Tuần này chưa có khoản chi nào.",
  disabled,
}: {
  transactions: Transaction[];
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  markedIds: ReadonlySet<string>;
  markLabel: string;
  checkboxLabel?: string;
  emptyText?: string;
  disabled?: boolean;
}) {
  if (transactions.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyText}</p>;
  }
  return (
    <ul className="flex max-h-80 flex-col divide-y overflow-y-auto rounded-lg border">
      {transactions.map((t) => {
        const checked = selected.has(t.id);
        return (
          <li key={t.id}>
            <label
              className={cn(
                "flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-muted/50",
                checked && "bg-muted",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={checked}
                disabled={disabled}
                onChange={() => onToggle(t.id)}
                aria-label={`${checkboxLabel}: ${t.note ?? t.category.name}`}
              />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate">{t.note ?? t.category.name}</span>
                <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  {t.category.name} · {formatDate(t.occurred_on)}
                  {t.spending_type && <SpendingTypeBadge value={t.spending_type} />}
                  {markedIds.has(t.id) && <Badge variant="outline">{markLabel}</Badge>}
                </span>
              </span>
              <span className="tabular-nums">{formatVND(t.amount)}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}
