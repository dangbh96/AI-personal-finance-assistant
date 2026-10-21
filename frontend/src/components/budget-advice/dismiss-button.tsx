"use client";

import { XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  apiRequest,
  describeError,
  type BudgetAdvice,
  type BudgetAdviceDismissRequest,
} from "@/lib/api";

const MAX_REASON = 500;

/** Bỏ qua advice (kèm ghi chú tuỳ chọn) — không đổi ngân sách. */
export function DismissButton({
  advice,
  onDismissed,
}: {
  advice: BudgetAdvice;
  onDismissed: (advice: BudgetAdvice) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const primary = advice.verdict !== "adjust_budget";

  async function dismiss() {
    setSaving(true);
    setError(null);
    try {
      const body: BudgetAdviceDismissRequest = { reason: reason.trim() || null };
      const saved = await apiRequest<BudgetAdvice>(
        "POST",
        `/budget/advice/${advice.id}/dismiss`,
        body,
      );
      setOpen(false);
      onDismissed(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Button variant={primary ? "secondary" : "outline"} onClick={() => setOpen(true)}>
        <XIcon />
        {advice.verdict === "on_track" ? "Đã xem" : "Bỏ qua"}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setError(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Bỏ qua tư vấn {advice.allocation_label}?</DialogTitle>
            <DialogDescription>
              Ngân sách giữ nguyên. Tư vấn chuyển sang mục “Đã bỏ qua” và vẫn xem lại được.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`dismiss-reason-${advice.id}`}>Ghi chú (không bắt buộc)</Label>
            <textarea
              id={`dismiss-reason-${advice.id}`}
              value={reason}
              maxLength={MAX_REASON}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Vd: khoản một lần, đã tính trước"
              className="min-h-20 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button onClick={dismiss} disabled={saving}>
              {saving ? "Đang lưu…" : "Bỏ qua tư vấn"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
