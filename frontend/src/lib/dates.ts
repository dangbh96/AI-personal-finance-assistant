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
