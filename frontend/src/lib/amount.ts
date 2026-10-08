/**
 * Parser số tiền gõ tắt phía client — chỉ là tiện ích nhập liệu, backend vẫn nhận số nguyên đồng.
 *
 *   "55000" | "55.000" | "55,000" → 55000
 *   "55k" | "55 nghìn"            → 55000
 *   "1tr5" | "1.5tr" | "1,5 triệu" → 1500000
 *   "1tr250"                       → 1250000
 *   "25 triệu" | "25m"             → 25000000
 *   "1 củ" → 1000000 · "2 lít" → 200000 · "1 tỷ" → 1000000000
 *
 * Trả `null` nếu không hiểu được hoặc kết quả không phải số nguyên dương.
 */

const UNITS: Record<string, number> = {
  k: 1_000,
  nghin: 1_000,
  ngan: 1_000,
  lit: 100_000,
  tr: 1_000_000,
  trieu: 1_000_000,
  cu: 1_000_000,
  m: 1_000_000,
  ty: 1_000_000_000,
};

const PATTERN =
  /^(\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|lit|tr|trieu|cu|m|ty)?\s*(\d+)?$/;

function normalize(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/(vnd|dong|d)$/, "")
    .trim();
}

export function parseAmountInput(input: string): number | null {
  const text = normalize(input);
  if (!text) return null;

  // Không có đơn vị: dấu . và , là phân cách hàng nghìn.
  if (/^\d{1,3}([.,]\d{3})+$|^\d+$/.test(text)) {
    const value = Number(text.replace(/[.,]/g, ""));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  }

  const match = PATTERN.exec(text);
  if (!match) return null;
  const [, numberPart, unit, tail] = match;
  if (!unit) return null;
  if (tail && /[.,]/.test(numberPart)) return null;

  const multiplier = UNITS[unit];
  const [intPart, fracPart = ""] = numberPart.split(/[.,]/);
  // "1tr5" → phần lẻ "5" của triệu (= 1.5tr); "1tr250" → 1.25tr.
  const fraction = tail ?? fracPart;

  let value = Number(intPart) * multiplier;
  if (fraction) {
    value += Math.round((Number(fraction) * multiplier) / 10 ** fraction.length);
  }
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}
