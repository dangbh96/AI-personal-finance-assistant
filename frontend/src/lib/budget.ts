import type {
  AllocationGroup,
  AllocationTrackingStatus,
  BudgetAllocationDraft,
  BudgetAllocationInput,
  BudgetStatus,
  BudgetStrategy,
  PaceStatus,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatAmountPlain } from "@/lib/format";

export const STRATEGY_LABELS: Record<BudgetStrategy, string> = {
  envelope: "Hũ chi tiêu (Envelope/Jars)",
  fifty_thirty_twenty: "50/30/20",
  pyf: "Trả cho mình trước (Pay Yourself First)",
};

export const STRATEGY_DESCRIPTIONS: Record<BudgetStrategy, string> = {
  envelope:
    "Chia thu nhập vào 5 hũ: Thiết yếu, Vui chơi, Mua sắm, Tiết kiệm, Dự phòng.",
  fifty_thirty_twenty:
    "50% thiết yếu, 30% mong muốn, 20% tiết kiệm — một mốc tham khảo, không phải luật.",
  pyf: "Để riêng khoản tiết kiệm trước, phần còn lại mới chia cho chi tiêu.",
};

export const STRATEGIES = Object.keys(STRATEGY_LABELS) as BudgetStrategy[];

export const STATUS_LABELS: Record<BudgetStatus, string> = {
  draft: "Nháp",
  active: "Đang dùng",
  closed: "Đã đóng",
};

export const STATUS_CLASSES: Record<BudgetStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  active:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  closed: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

export const GROUP_LABELS: Record<AllocationGroup, string> = {
  essential: "Thiết yếu",
  wants: "Mong muốn",
  savings: "Tiết kiệm",
  irregular: "Bất thường",
};

export const TRACKING_STATUS_LABELS: Record<AllocationTrackingStatus, string> =
  {
    on_track: "Trong kế hoạch",
    ahead_of_pace: "Chi nhanh hơn nhịp",
    over_budget: "Vượt ngân sách",
    not_tracked: "Chưa theo dõi",
  };

export const TRACKING_STATUS_CLASSES: Record<AllocationTrackingStatus, string> =
  {
    on_track:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    ahead_of_pace:
      "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    over_budget: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300",
    not_tracked: "bg-muted text-muted-foreground",
  };

export const PACE_LABELS: Record<PaceStatus, string> = {
  ahead: "Nhanh hơn nhịp",
  on_track: "Đúng nhịp",
  under: "Chậm hơn nhịp",
};

/** Tên hũ preset (lưu tiếng Anh trong `jar_name`) → tên hiển thị. */
export const JAR_LABELS: Record<string, string> = {
  Essential: "Thiết yếu",
  Fun: "Vui chơi",
  Shopping: "Mua sắm",
  Saving: "Tiết kiệm",
  Unexpected: "Dự phòng",
};

type AllocationLike = Pick<BudgetAllocationDraft, "group" | "jar_name"> & {
  category?: { name: string; icon?: string | null } | null;
};

export function allocationLabel(allocation: AllocationLike): string {
  if (allocation.category) {
    return `${allocation.category.icon ?? ""} ${allocation.category.name}`.trim();
  }
  const jar = allocation.jar_name ?? "";
  if (jar in JAR_LABELS) return JAR_LABELS[jar];
  if (jar in GROUP_LABELS) return GROUP_LABELS[jar as AllocationGroup];
  return jar;
}

/** Ô số tiền ngân sách: như `parseAmountInput` nhưng chấp nhận 0. */
export function parseBudgetAmount(text: string): number | null {
  if (/^\s*0+\s*(đ|₫|d|vnd)?\s*$/i.test(text)) return 0;
  return parseAmountInput(text);
}

/** Dòng phân bổ đang chỉnh trên UI: phần định danh + chuỗi số tiền user gõ. */
export type AllocationRow = {
  group: AllocationGroup;
  category_id: string | null;
  category: BudgetAllocationDraft["category"];
  jar_name: string | null;
  amountText: string;
};

export function toRows(allocations: BudgetAllocationDraft[]): AllocationRow[] {
  return allocations.map((a) => ({
    group: a.group,
    category_id: a.category_id,
    category: a.category ?? null,
    jar_name: a.jar_name,
    amountText: formatAmountPlain(a.planned_amount),
  }));
}

/** `null` nếu có ô số tiền không hợp lệ. */
export function toAllocationInputs(
  rows: AllocationRow[],
): BudgetAllocationInput[] | null {
  const inputs: BudgetAllocationInput[] = [];
  for (const row of rows) {
    const amount = parseBudgetAmount(row.amountText);
    if (amount === null) return null;
    inputs.push({
      group: row.group,
      category_id: row.category_id,
      jar_name: row.jar_name,
      planned_amount: amount,
    });
  }
  return inputs;
}

/** "2026-10" → "2026-10-01" */
export function monthToPeriod(month: string): string {
  return `${month}-01`;
}
