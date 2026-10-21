import type { GoalStatus } from "@/lib/api";

export const GOAL_STATUS_LABELS: Record<GoalStatus, string> = {
  active: "Đang thực hiện",
  paused: "Tạm dừng",
  achieved: "Đã đạt",
};

export const GOAL_STATUS_TONES: Record<GoalStatus, string> = {
  active:
    "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300",
  paused: "border-border bg-muted text-muted-foreground",
  achieved:
    "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
};

export const ON_TRACK_TONE =
  "border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-300";
export const BEHIND_TONE =
  "border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300";

/** Số tháng còn lại (backend tính) → nhãn. */
export function describeMonthsRemaining(months: number, overdue: boolean): string {
  if (overdue) return "Đã quá hạn";
  return `Còn ${months} tháng`;
}
