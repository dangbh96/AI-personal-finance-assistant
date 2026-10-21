"use client";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  apiRequest,
  describeError,
  withQuery,
  type Goal,
  type GoalContribution,
  type GoalContributionCreate,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatVND } from "@/lib/format";

/** Khoản góp thủ công (không gắn thu nhập) — vd số tiền đã để dành sẵn cho mục tiêu. */
export function ContributionDialog({
  goal,
  today,
  onOpenChange,
  onSaved,
}: {
  /** `null` = đóng. */
  goal: Goal | null;
  today: string;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  return (
    <Dialog open={goal !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Thêm khoản góp{goal ? ` — ${goal.name}` : ""}</DialogTitle>
          <DialogDescription>
            Ghi số tiền bạn đã để dành cho mục tiêu này
            {goal ? ` (còn thiếu ${formatVND(goal.remaining_amount)})` : ""}.
          </DialogDescription>
        </DialogHeader>
        {goal && (
          <ContributionForm
            key={goal.id}
            goal={goal}
            today={today}
            onCancel={() => onOpenChange(false)}
            onSaved={() => {
              onSaved();
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ContributionForm({
  goal,
  today,
  onCancel,
  onSaved,
}: {
  goal: Goal;
  today: string;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [amountText, setAmountText] = useState("");
  const [day, setDay] = useState(today);
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const amount = parseAmountInput(amountText);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (amount === null || !day) return;
    setSaving(true);
    try {
      await apiRequest<GoalContribution>(
        "POST",
        withQuery(`/goals/${goal.id}/contributions`, { today }),
        { amount, contributed_on: day } satisfies GoalContributionCreate,
      );
      onSaved();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="contribution-amount">Số tiền</Label>
        <Input
          id="contribution-amount"
          inputMode="decimal"
          autoComplete="off"
          placeholder="8tr"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          aria-invalid={submitted && amount === null}
        />
        <p
          className={
            submitted && amount === null
              ? "text-xs text-destructive"
              : "text-xs text-muted-foreground"
          }
        >
          {amount !== null
            ? `= ${formatVND(amount)}`
            : submitted
              ? "Số tiền phải là số nguyên dương"
              : "Ví dụ: 8tr, 500k"}
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="contribution-date">Ngày</Label>
        <Input
          id="contribution-date"
          type="date"
          max={today}
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Huỷ
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? "Đang lưu…" : "Thêm khoản góp"}
        </Button>
      </DialogFooter>
    </form>
  );
}
