import type { ZoneMode, ZoneStatus } from "@/lib/api";

/** Nhãn vùng linh hoạt (Phase 9). Trạng thái do backend tính — frontend chỉ hiển thị. */
export const ZONE_LABELS: Record<ZoneStatus, string> = {
  normal: "Trong vùng thoải mái",
  attention: "Đã vượt vùng thoải mái",
  review_needed: "Vượt ngưỡng cảnh báo",
};

export const ZONE_ICONS: Record<ZoneStatus, string> = {
  normal: "🟢",
  attention: "🟡",
  review_needed: "🔴",
};

export const ZONE_CLASSES: Record<ZoneStatus, string> = {
  normal:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  attention: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  review_needed: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
};

export const ZONE_MODE_LABELS: Record<ZoneMode, string> = {
  auto: "Auto",
  manual: "Thủ công",
};

export const AUTO_ZONE_HINT =
  "Tính từ 3–6 tháng gần nhất, không tính khoản bất thường.";
