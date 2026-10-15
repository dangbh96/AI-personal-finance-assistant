import type { Direction, SpendingType, TransactionSource } from "@/lib/api";

export const DIRECTION_LABELS: Record<Direction, string> = {
  income: "Thu nhập",
  expense: "Chi tiêu",
};

export const SOURCE_LABELS: Record<TransactionSource, string> = {
  manual: "Thủ công",
  nl: "Câu tự nhiên",
  receipt: "Hoá đơn",
  import: "Import",
  recurring: "Định kỳ",
};

export const SPENDING_TYPE_LABELS: Record<SpendingType, string> = {
  essential: "Thiết yếu",
  non_essential: "Không thiết yếu",
  irregular: "Bất thường",
};

export const SPENDING_TYPE_CLASSES: Record<SpendingType, string> = {
  essential: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  non_essential:
    "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  irregular:
    "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
};

export const SPENDING_TYPES = Object.keys(
  SPENDING_TYPE_LABELS,
) as SpendingType[];
