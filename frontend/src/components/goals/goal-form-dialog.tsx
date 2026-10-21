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
  type GoalCreate,
  type GoalUpdate,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatAmountPlain, formatVND } from "@/lib/format";

/** Tạo (`goal = null`) / sửa mục tiêu: tên, số tiền mục tiêu (gõ tắt 30tr), hạn, ưu tiên. */
export function GoalFormDialog({
  open,
  goal,
  today,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  goal: Goal | null;
  today: string;
  onOpenChange: (open: boolean) => void;
  onSaved: (goal: Goal) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{goal ? "Sửa mục tiêu" : "Tạo mục tiêu tiết kiệm"}</DialogTitle>
          <DialogDescription>
            App tính số tiền nên để dành mỗi tháng để kịp hạn. Số tiền có thể gõ tắt: 30tr, 1tr5…
          </DialogDescription>
        </DialogHeader>
        {open && (
          <GoalForm
            key={goal?.id ?? "new"}
            goal={goal}
            today={today}
            onCancel={() => onOpenChange(false)}
            onSaved={(saved) => {
              onSaved(saved);
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function GoalForm({
  goal,
  today,
  onCancel,
  onSaved,
}: {
  goal: Goal | null;
  today: string;
  onCancel: () => void;
  onSaved: (goal: Goal) => void;
}) {
  const [name, setName] = useState(goal?.name ?? "");
  const [targetText, setTargetText] = useState(
    goal ? formatAmountPlain(goal.target_amount) : "",
  );
  const [deadline, setDeadline] = useState(goal?.deadline ?? "");
  const [priority, setPriority] = useState(String(goal?.priority ?? 1));
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const target = parseAmountInput(targetText);
  const priorityValue = Number(priority);
  const errors = {
    name: name.trim() ? undefined : "Nhập tên mục tiêu",
    target: target === null ? "Số tiền phải là số nguyên dương" : undefined,
    deadline: deadline ? undefined : "Chọn hạn",
    priority:
      Number.isInteger(priorityValue) && priorityValue >= 1 && priorityValue <= 100
        ? undefined
        : "Ưu tiên từ 1 (cao nhất) tới 100",
  };
  const valid = !errors.name && !errors.target && !errors.deadline && !errors.priority;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!valid || target === null) return;
    setSaving(true);
    try {
      const path = withQuery(goal ? `/goals/${goal.id}` : "/goals", { today });
      const saved = goal
        ? await apiRequest<Goal>("PATCH", path, {
            name: name.trim(),
            target_amount: target,
            deadline,
            priority: priorityValue,
          } satisfies GoalUpdate)
        : await apiRequest<Goal>("POST", path, {
            name: name.trim(),
            target_amount: target,
            deadline,
            priority: priorityValue,
          } satisfies GoalCreate);
      onSaved(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const show = (message: string | undefined) =>
    submitted && message ? (
      <p className="text-xs text-destructive">{message}</p>
    ) : null;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="goal-name">Tên mục tiêu</Label>
        <Input
          id="goal-name"
          maxLength={100}
          placeholder="Laptop"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-invalid={submitted && !!errors.name}
        />
        {show(errors.name)}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="goal-target">Số tiền mục tiêu</Label>
        <Input
          id="goal-target"
          inputMode="decimal"
          autoComplete="off"
          placeholder="30tr"
          value={targetText}
          onChange={(e) => setTargetText(e.target.value)}
          aria-invalid={submitted && !!errors.target}
        />
        {submitted && errors.target ? (
          show(errors.target)
        ) : (
          <p className="text-xs text-muted-foreground">
            {target !== null ? `= ${formatVND(target)}` : "Ví dụ: 30tr, 12.000.000"}
          </p>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="goal-deadline">Hạn</Label>
          <Input
            id="goal-deadline"
            type="date"
            min={today}
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
            aria-invalid={submitted && !!errors.deadline}
          />
          {show(errors.deadline)}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="goal-priority">Ưu tiên (1 = cao nhất)</Label>
          <Input
            id="goal-priority"
            type="number"
            min={1}
            max={100}
            step={1}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            aria-invalid={submitted && !!errors.priority}
          />
          {show(errors.priority)}
        </div>
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
          {saving ? "Đang lưu…" : goal ? "Lưu thay đổi" : "Tạo mục tiêu"}
        </Button>
      </DialogFooter>
    </form>
  );
}
