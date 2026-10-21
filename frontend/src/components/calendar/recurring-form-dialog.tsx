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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  apiRequest,
  describeError,
  withQuery,
  type Category,
  type Direction,
  type RecurringCreate,
  type RecurringFrequency,
  type RecurringTransaction,
  type RecurringUpdate,
  type SpendingType,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { FREQUENCY_LABELS, WEEKDAY_LABELS } from "@/lib/calendar";
import { formatAmountPlain, formatVND } from "@/lib/format";
import { DIRECTION_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

const FREQUENCY_ITEMS = FREQUENCY_LABELS as Record<string, string>;
const WEEKDAY_ITEMS = Object.fromEntries(
  Object.entries(WEEKDAY_LABELS).map(([k, v]) => [k, v]),
) as Record<string, string>;
const SPENDING_TYPE_ITEMS = SPENDING_TYPE_LABELS as Record<string, string>;

/** Tạo (`item = null`) / sửa khoản định kỳ: tiền nhà, internet, lương, subscription… */
export function RecurringFormDialog({
  open,
  item,
  categories,
  today,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  item: RecurringTransaction | null;
  categories: Category[];
  today: string;
  onOpenChange: (open: boolean) => void;
  onSaved: (item: RecurringTransaction) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{item ? "Sửa khoản định kỳ" : "Thêm khoản định kỳ"}</DialogTitle>
          <DialogDescription>
            Khoản lặp lại đều đặn (lương, tiền nhà, internet…). Ngày 31 sẽ thành ngày cuối ở tháng
            ngắn. Bỏ trống “kỳ tới” để app tự tính kỳ đầu tiên sau hôm nay.
          </DialogDescription>
        </DialogHeader>
        {open && (
          <RecurringForm
            key={item?.id ?? "new"}
            item={item}
            categories={categories}
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

function RecurringForm({
  item,
  categories,
  today,
  onCancel,
  onSaved,
}: {
  item: RecurringTransaction | null;
  categories: Category[];
  today: string;
  onCancel: () => void;
  onSaved: (item: RecurringTransaction) => void;
}) {
  const [name, setName] = useState(item?.name ?? "");
  const [direction, setDirection] = useState<Direction>(item?.direction ?? "expense");
  const [categoryId, setCategoryId] = useState<string | null>(item?.category_id ?? null);
  const [spendingType, setSpendingType] = useState<SpendingType | null>(
    item?.spending_type ?? null,
  );
  const [amountText, setAmountText] = useState(item ? formatAmountPlain(item.amount) : "");
  const [frequency, setFrequency] = useState<RecurringFrequency>(item?.frequency ?? "monthly");
  const [dayOfMonth, setDayOfMonth] = useState(String(item?.day_of_month ?? ""));
  const [dayOfWeek, setDayOfWeek] = useState<string | null>(
    item?.day_of_week ? String(item.day_of_week) : null,
  );
  const [nextDueOn, setNextDueOn] = useState(item?.next_due_on ?? "");
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = categories.filter(
    (c) => c.kind === direction && (!c.is_archived || c.id === item?.category_id),
  );
  const categoryItems = Object.fromEntries(
    options.map((c) => [c.id, `${c.icon ?? ""} ${c.name}`.trim()]),
  );
  const amount = parseAmountInput(amountText);
  const dom = Number(dayOfMonth);
  const domValid = Number.isInteger(dom) && dom >= 1 && dom <= 31;
  const errors = {
    name: name.trim() ? undefined : "Nhập tên",
    amount: amount === null ? "Số tiền phải là số nguyên dương" : undefined,
    category: categoryId ? undefined : "Chọn danh mục",
    day:
      frequency === "weekly"
        ? dayOfWeek || nextDueOn
          ? undefined
          : "Chọn thứ"
        : frequency === "yearly"
          ? nextDueOn
            ? undefined
            : "Khoản hằng năm cần ngày kỳ tới"
          : domValid || (!dayOfMonth && nextDueOn)
            ? undefined
            : "Ngày từ 1 tới 31",
  };
  const valid = !errors.name && !errors.amount && !errors.category && !errors.day;

  function changeDirection(next: Direction) {
    if (next === direction) return;
    setDirection(next);
    setCategoryId(null);
    setSpendingType(null);
  }

  function changeCategory(id: string | null) {
    setCategoryId(id);
    const category = categories.find((c) => c.id === id);
    if (direction === "expense" && category?.default_spending_type) {
      setSpendingType(category.default_spending_type);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
    setError(null);
    if (!valid || amount === null || !categoryId) return;
    const schedule = {
      frequency,
      day_of_month: frequency === "weekly" || !dayOfMonth ? null : dom,
      day_of_week: frequency === "weekly" && dayOfWeek ? Number(dayOfWeek) : null,
    };
    const common = {
      name: name.trim(),
      direction,
      amount,
      category_id: categoryId,
      spending_type: direction === "expense" ? spendingType : null,
      ...schedule,
    };
    setSaving(true);
    try {
      let saved: RecurringTransaction;
      if (item) {
        const body: RecurringUpdate = { ...common };
        if (nextDueOn && nextDueOn !== item.next_due_on) body.next_due_on = nextDueOn;
        saved = await apiRequest<RecurringTransaction>(
          "PATCH",
          withQuery(`/recurring-transactions/${item.id}`, { today }),
          body,
        );
      } else {
        const body: RecurringCreate = { ...common, next_due_on: nextDueOn || null };
        saved = await apiRequest<RecurringTransaction>(
          "POST",
          withQuery("/recurring-transactions", { today }),
          body,
        );
      }
      onSaved(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const show = (message: string | undefined) =>
    submitted && message ? <p className="text-xs text-destructive">{message}</p> : null;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <div
        role="radiogroup"
        aria-label="Thu hay chi"
        className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1"
      >
        {(["expense", "income"] as const).map((d) => (
          <button
            key={d}
            type="button"
            role="radio"
            aria-checked={direction === d}
            onClick={() => changeDirection(d)}
            className={cn(
              "h-7 rounded-md text-sm font-medium transition-colors",
              direction === d
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground",
              direction === d && d === "income" && "text-emerald-600",
              direction === d && d === "expense" && "text-rose-600",
            )}
          >
            {DIRECTION_LABELS[d]}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rec-name">Tên</Label>
          <Input
            id="rec-name"
            maxLength={100}
            placeholder={direction === "income" ? "Lương" : "Tiền nhà"}
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={submitted && !!errors.name}
          />
          {show(errors.name)}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rec-amount">Số tiền</Label>
          <Input
            id="rec-amount"
            inputMode="decimal"
            autoComplete="off"
            placeholder="5tr"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            aria-invalid={submitted && !!errors.amount}
          />
          {submitted && errors.amount ? (
            show(errors.amount)
          ) : (
            <p className="text-xs text-muted-foreground">
              {amount !== null ? `= ${formatVND(amount)}` : "Ví dụ: 5tr, 300k"}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rec-category">Danh mục</Label>
          <Select
            items={categoryItems}
            value={categoryId}
            onValueChange={(v) => changeCategory(v as string | null)}
          >
            <SelectTrigger
              id="rec-category"
              className="w-full"
              aria-invalid={submitted && !!errors.category}
            >
              <SelectValue placeholder="Chọn danh mục" />
            </SelectTrigger>
            <SelectContent>
              {options.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {categoryItems[c.id]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {show(errors.category)}
        </div>
        {direction === "expense" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rec-spending-type">Loại chi tiêu</Label>
            <Select
              items={SPENDING_TYPE_ITEMS}
              value={spendingType}
              onValueChange={(v) => setSpendingType(v as SpendingType | null)}
            >
              <SelectTrigger id="rec-spending-type" className="w-full">
                <SelectValue placeholder="Theo mặc định của danh mục" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SPENDING_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rec-frequency">Lặp lại</Label>
          <Select
            items={FREQUENCY_ITEMS}
            value={frequency}
            onValueChange={(v) => v && setFrequency(v as RecurringFrequency)}
          >
            <SelectTrigger id="rec-frequency" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(FREQUENCY_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {frequency === "weekly" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rec-dow">Thứ</Label>
            <Select
              items={WEEKDAY_ITEMS}
              value={dayOfWeek}
              onValueChange={(v) => setDayOfWeek(v as string | null)}
            >
              <SelectTrigger
                id="rec-dow"
                className="w-full"
                aria-invalid={submitted && !!errors.day}
              >
                <SelectValue placeholder="Chọn thứ" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(WEEKDAY_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {show(errors.day)}
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rec-dom">Ngày trong tháng</Label>
            <Input
              id="rec-dom"
              type="number"
              min={1}
              max={31}
              placeholder={frequency === "yearly" ? "theo ngày kỳ tới" : "5"}
              value={dayOfMonth}
              onChange={(e) => setDayOfMonth(e.target.value)}
              aria-invalid={submitted && !!errors.day}
            />
            {frequency === "monthly" && show(errors.day)}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rec-next">Kỳ tới {frequency === "yearly" ? "" : "(tuỳ chọn)"}</Label>
          <Input
            id="rec-next"
            type="date"
            value={nextDueOn}
            onChange={(e) => setNextDueOn(e.target.value)}
            aria-invalid={submitted && frequency === "yearly" && !!errors.day}
          />
          {frequency === "yearly" ? (
            show(errors.day)
          ) : (
            <p className="text-xs text-muted-foreground">Phải đúng ngày / thứ đã chọn.</p>
          )}
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
          {saving ? "Đang lưu…" : item ? "Lưu thay đổi" : "Thêm khoản định kỳ"}
        </Button>
      </DialogFooter>
    </form>
  );
}
