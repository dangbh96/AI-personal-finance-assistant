import { cn } from "@/lib/utils";
import type { SpendingType } from "@/lib/api";
import { SPENDING_TYPE_CLASSES, SPENDING_TYPE_LABELS } from "@/lib/labels";

export function SpendingTypeBadge({
  value,
  className,
}: {
  value: SpendingType;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-4xl px-2 text-xs font-medium whitespace-nowrap",
        SPENDING_TYPE_CLASSES[value],
        className,
      )}
    >
      {SPENDING_TYPE_LABELS[value]}
    </span>
  );
}
