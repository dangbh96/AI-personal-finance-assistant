function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Ngày hôm nay theo giờ máy, dạng "YYYY-MM-DD". */
export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Tháng hiện tại, dạng "YYYY-MM". */
export function currentMonth(): string {
  return todayISO().slice(0, 7);
}

/** "2026-02" → { from: "2026-02-01", to: "2026-02-28" } */
export function monthToRange(month: string): { from: string; to: string } {
  const [y, m] = month.split("-").map(Number);
  const lastDay = new Date(y, m, 0).getDate();
  return { from: `${month}-01`, to: `${month}-${pad(lastDay)}` };
}

/** Cộng/trừ tháng: shiftMonth("2026-01", -1) → "2025-12" */
export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`;
}

// Ngày lịch tính theo UTC để không lệch múi giờ (chỉ dùng cho điều hướng, không tính tiền).
function parseISO(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function toISO(date: Date): string {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

/** Cộng/trừ ngày: addDays("2026-10-12", 6) → "2026-10-18" */
export function addDays(iso: string, days: number): string {
  const date = parseISO(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return toISO(date);
}

/** Thứ Hai của tuần chứa ngày `iso` (tuần bắt đầu Thứ Hai). */
export function weekStartOf(iso: string): string {
  const weekday = (parseISO(iso).getUTCDay() + 6) % 7; // Thứ Hai = 0
  return addDays(iso, -weekday);
}

export function isMonday(iso: string): boolean {
  return parseISO(iso).getUTCDay() === 1;
}

/** "2026-10-12" → "12/10–18/10/2026" */
export function formatWeekRange(weekStart: string): string {
  const end = addDays(weekStart, 6);
  const [, sm, sd] = weekStart.split("-");
  const [ey, em, ed] = end.split("-");
  return `${sd}/${sm}–${ed}/${em}/${ey}`;
}
