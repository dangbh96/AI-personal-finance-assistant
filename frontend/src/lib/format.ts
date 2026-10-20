const vndFormatter = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
});

/** 1500000 → "1.500.000 ₫" */
export function formatVND(amount: number): string {
  return vndFormatter.format(amount);
}

const plainFormatter = new Intl.NumberFormat("vi-VN");

/** 1500000 → "1.500.000" (giá trị ban đầu cho ô nhập số tiền). */
export function formatAmountPlain(amount: number): string {
  return plainFormatter.format(amount);
}

/** 1500000 → "+1.500.000 ₫", -300000 → "−300.000 ₫", 0 → "0 ₫" */
export function formatSignedVND(amount: number): string {
  if (amount === 0) return formatVND(0);
  return `${amount > 0 ? "+" : "−"}${formatVND(Math.abs(amount))}`;
}

const percentFormatter = new Intl.NumberFormat("vi-VN", {
  maximumFractionDigits: 1,
});

/** 112.5 → "112,5%" (giá trị đã là phần trăm do backend tính). */
export function formatPercent(value: number): string {
  return `${percentFormatter.format(value)}%`;
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
