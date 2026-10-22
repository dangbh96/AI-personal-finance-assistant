import { parseAmountInput } from "@/lib/amount";
import type { SimulationParam } from "@/lib/api";

export type ParamType = SimulationParam["type"];

export const MAX_PARAMS = 10;

export const PARAM_LABELS: Record<ParamType, string> = {
  reduce_category: "Giảm chi một danh mục (%)",
  change_income: "Thay đổi thu nhập / tháng",
  add_recurring_expense: "Thêm khoản chi định kỳ / tháng",
  change_goal_deadline: "Đổi hạn mục tiêu",
};

/** Một dòng kịch bản trên form (chuỗi thô để giữ nguyên thứ user gõ). */
export type ParamRow = {
  key: string;
  type: ParamType;
  categoryId: string;
  percent: string;
  incomeSign: "up" | "down";
  amountText: string;
  name: string;
  goalId: string;
  deadline: string;
};

export function newRow(type: ParamType = "reduce_category", key?: string): ParamRow {
  return {
    // Dòng ban đầu cần key cố định (render trên server và client phải giống nhau).
    key: key ?? crypto.randomUUID(),
    type,
    categoryId: "",
    percent: "20",
    incomeSign: "up",
    amountText: "",
    name: "",
    goalId: "",
    deadline: "",
  };
}

/** Dòng form → tham số API; trả chuỗi lỗi nếu dòng chưa hợp lệ. */
export function toParam(row: ParamRow): SimulationParam | string {
  switch (row.type) {
    case "reduce_category": {
      const percent = Number(row.percent);
      if (!row.categoryId) return "Chọn danh mục cần giảm";
      if (!Number.isInteger(percent) || percent < 1 || percent > 100) {
        return "Phần trăm giảm phải là số nguyên từ 1 đến 100";
      }
      return { type: "reduce_category", category_id: row.categoryId, percent };
    }
    case "change_income": {
      const amount = parseAmountInput(row.amountText);
      if (amount === null) return "Nhập số tiền thu nhập thay đổi (vd 2tr)";
      return {
        type: "change_income",
        delta_amount: row.incomeSign === "up" ? amount : -amount,
      };
    }
    case "add_recurring_expense": {
      const amount = parseAmountInput(row.amountText);
      if (!row.name.trim()) return "Nhập tên khoản chi mới";
      if (amount === null) return "Nhập số tiền mỗi tháng (vd 199k)";
      if (!row.categoryId) return "Chọn danh mục của khoản chi mới";
      return {
        type: "add_recurring_expense",
        name: row.name.trim(),
        amount,
        category_id: row.categoryId,
      };
    }
    case "change_goal_deadline":
      if (!row.goalId) return "Chọn mục tiêu";
      if (!row.deadline) return "Chọn hạn mới";
      return {
        type: "change_goal_deadline",
        goal_id: row.goalId,
        new_deadline: row.deadline,
      };
  }
}

/** Tham số đã lưu → dòng form (mở lại kịch bản). */
export function fromParam(param: SimulationParam): ParamRow {
  const row = newRow(param.type);
  switch (param.type) {
    case "reduce_category":
      return {
        ...row,
        categoryId: param.category_id,
        percent: String(param.percent),
      };
    case "change_income":
      return {
        ...row,
        incomeSign: param.delta_amount >= 0 ? "up" : "down",
        amountText: String(Math.abs(param.delta_amount)),
      };
    case "add_recurring_expense":
      return {
        ...row,
        name: param.name,
        amountText: String(param.amount),
        categoryId: param.category_id,
      };
    case "change_goal_deadline":
      return { ...row, goalId: param.goal_id, deadline: param.new_deadline };
  }
}
