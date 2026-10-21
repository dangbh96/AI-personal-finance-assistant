import type { AdviceStatus, AdviceVerdict } from "@/lib/api";

/** Nhãn badge verdict (phase-08 § 4.4) — verdict do backend tính, UI chỉ hiển thị. */
export const VERDICT_LABELS: Record<AdviceVerdict, string> = {
  adjust_budget: "Budget có thể thấp hơn thực tế",
  one_off: "Khoản bất thường một lần",
  adjust_behavior: "Nên xem lại hành vi/nhịp chi",
  on_track: "Đang trong kế hoạch",
};

export const VERDICT_CLASSES: Record<AdviceVerdict, string> = {
  adjust_budget: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  one_off:
    "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300",
  adjust_behavior:
    "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  on_track:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
};

export const ADVICE_STATUS_LABELS: Record<AdviceStatus, string> = {
  open: "Chờ quyết định",
  accepted: "Đã áp dụng",
  dismissed: "Đã bỏ qua",
};

/** Bộ lọc trạng thái trên trang (`all` = không lọc). */
export const ADVICE_STATUS_FILTERS = ["open", "accepted", "dismissed", "all"] as const;
export type AdviceStatusFilter = (typeof ADVICE_STATUS_FILTERS)[number];

export const ADVICE_STATUS_FILTER_LABELS: Record<AdviceStatusFilter, string> = {
  open: "Chờ quyết định",
  accepted: "Đã áp dụng",
  dismissed: "Đã bỏ qua",
  all: "Tất cả",
};

export function isAdviceStatusFilter(value: string | null): value is AdviceStatusFilter {
  return ADVICE_STATUS_FILTERS.includes(value as AdviceStatusFilter);
}
