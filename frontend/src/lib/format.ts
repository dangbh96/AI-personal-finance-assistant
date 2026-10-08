const vndFormatter = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
});

/** 1500000 → "1.500.000 ₫" */
export function formatVND(amount: number): string {
  return vndFormatter.format(amount);
}

/** "2026-10-07" → "07/10/2026" (không qua Date để tránh lệch múi giờ). */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}/${m}/${y}`;
}

/** "2026-10" → "Tháng 10/2026" */
export function formatMonthLabel(month: string): string {
  const [y, m] = month.split("-");
  return `Tháng ${Number(m)}/${y}`;
}
