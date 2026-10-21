"use client";

import { CheckIcon } from "lucide-react";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  apiRequest,
  describeError,
  type BudgetAdvice,
  type BudgetAdviceAcceptRequest,
  type BudgetAdviceAcceptResult,
} from "@/lib/api";
import { shiftMonth } from "@/lib/dates";
import { formatMonthLabel, formatVND } from "@/lib/format";

/**
 * Nút "Áp dụng" + hộp xác nhận: chỉ khi user bấm xác nhận mới gửi `confirm: true` (phase-08
 * § 4.2). Planned mới vượt thu nhập dự kiến → backend trả `planned_exceeds_income`, user tick
 * thêm một xác nhận rồi gửi lại.
 */
export function AcceptAdviceDialog({
  advice,
  onAccepted,
}: {
  advice: BudgetAdvice;
  onAccepted: (result: BudgetAdviceAcceptResult) => void;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overIncome, setOverIncome] = useState(false);
  const [confirmOverIncome, setConfirmOverIncome] = useState(false);

  const proposed = advice.evidence.proposed_planned_amount;
  const targetMonth = shiftMonth(advice.month.slice(0, 7), 1);
  const targetLabel = formatMonthLabel(targetMonth).toLowerCase();
  if (proposed == null) return null;

  function reset(next: boolean) {
    setOpen(next);
    if (!next) {
      setError(null);
      setOverIncome(false);
      setConfirmOverIncome(false);
    }
  }

  async function accept() {
    setSaving(true);
    setError(null);
    try {
      const body: BudgetAdviceAcceptRequest = {
        confirm: true,
        target_month: `${targetMonth}-01`,
        confirm_over_income: confirmOverIncome,
      };
      const result = await apiRequest<BudgetAdviceAcceptResult>(
        "POST",
        `/budget/advice/${advice.id}/accept`,
        body,
      );
      reset(false);
      onAccepted(result);
    } catch (err) {
      if (err instanceof ApiError && err.code === "planned_exceeds_income") {
        setOverIncome(true);
      }
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Button onClick={() => reset(true)}>
        <CheckIcon />
        Áp dụng {formatVND(proposed)} cho {targetLabel}
      </Button>
      <AlertDialog open={open} onOpenChange={reset}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Áp dụng ngân sách mới?</AlertDialogTitle>
            <AlertDialogDescription>
              Đặt kế hoạch <strong>{advice.allocation_label}</strong> {targetLabel} thành{" "}
              <strong>{formatVND(proposed)}</strong> (hiện {formatVND(advice.evidence.planned_amount)}).
              Nếu {targetLabel} chưa có ngân sách, app sẽ tạo bản nháp copy từ{" "}
              {formatMonthLabel(advice.month.slice(0, 7)).toLowerCase()} rồi sửa dòng này. Ngân sách
              tháng đang xem không thay đổi.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {overIncome && (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4 accent-primary"
                checked={confirmOverIncome}
                onChange={(e) => setConfirmOverIncome(e.target.checked)}
              />
              Tôi vẫn muốn áp dụng dù tổng kế hoạch vượt thu nhập dự kiến.
            </label>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction
              onClick={accept}
              disabled={saving || (overIncome && !confirmOverIncome)}
            >
              {saving ? "Đang áp dụng…" : "Xác nhận áp dụng"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
