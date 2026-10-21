import type {
  CalendarEventKind,
  RecurringDueStatus,
  RecurringFrequency,
} from "@/lib/api";

export const FREQUENCY_LABELS: Record<RecurringFrequency, string> = {
  monthly: "Hằng tháng",
  weekly: "Hằng tuần",
  yearly: "Hằng năm",
};

/** ISO: Thứ Hai = 1 … Chủ Nhật = 7. */
export const WEEKDAY_LABELS: Record<number, string> = {
  1: "Thứ Hai",
  2: "Thứ Ba",
  3: "Thứ Tư",
  4: "Thứ Năm",
  5: "Thứ Sáu",
  6: "Thứ Bảy",
  7: "Chủ Nhật",
};

export const WEEKDAY_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

export const DUE_STATUS_LABELS: Record<RecurringDueStatus, string> = {
  overdue: "Quá hạn",
  due_today: "Hôm nay",
  upcoming: "Sắp đến",
  later: "Còn xa",
};

export const EVENT_KIND_LABELS: Record<CalendarEventKind, string> = {
  recurring: "Sắp tới",
  paid: "Đã ghi",
  goal_saving: "Để dành",
};

/** "Hằng tháng · ngày 31" / "Hằng tuần · Thứ Hai" / "Hằng năm · 28/02". */
export function describeSchedule(item: {
  frequency: RecurringFrequency;
  day_of_month?: number | null;
  day_of_week?: number | null;
  next_due_on: string;
}): string {
  const label = FREQUENCY_LABELS[item.frequency];
  if (item.frequency === "weekly") {
    return `${label} · ${WEEKDAY_LABELS[item.day_of_week ?? 1]}`;
  }
  if (item.frequency === "yearly") {
    const [, m] = item.next_due_on.split("-");
    return `${label} · ${String(item.day_of_month).padStart(2, "0")}/${m}`;
  }
  return `${label} · ngày ${item.day_of_month}`;
}

/** "2026-10-05" → "05/10" */
export function formatDayMonth(isoDate: string): string {
  const [, m, d] = isoDate.split("-");
  return `${d}/${m}`;
}

/**
 * Ô lịch của tháng "YYYY-MM" (tuần bắt đầu Thứ Hai): ngày ISO hoặc `null` cho ô trống đầu /
 * cuối. Chỉ dùng để vẽ, không tính tiền.
 */
export function monthGrid(month: string): (string | null)[] {
  const [y, m] = month.split("-").map(Number);
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= days; d++) {
    cells.push(`${month}-${String(d).padStart(2, "0")}`);
  }
  while (cells.length % 7) cells.push(null);
  return cells;
}

/**
 * Số dư nhập tay: như `parseAmountInput` nhưng cho phép 0 và số âm ("-2tr").
 * Trả `null` nếu không hiểu được.
 */
export function parseBalanceInput(
  input: string,
  parseAmount: (text: string) => number | null,
): number | null {
  const text = input.trim();
  if (/^0+$/.test(text)) return 0;
  if (text.startsWith("-") || text.startsWith("−")) {
    const value = parseAmount(text.slice(1));
    return value === null ? null : -value;
  }
  return parseAmount(text);
}
