"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Category, Goal } from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { formatVND } from "@/lib/format";
import {
  MAX_PARAMS,
  newRow,
  PARAM_LABELS,
  type ParamRow,
  type ParamType,
} from "@/lib/simulator";

const SELECT =
  "h-9 rounded-md border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-ring";

/** Danh sách thay đổi của kịch bản (áp dụng theo thứ tự từ trên xuống). */
export function ScenarioForm({
  rows,
  onChange,
  categories,
  goals,
  today,
}: {
  rows: ParamRow[];
  onChange: (rows: ParamRow[]) => void;
  categories: Category[];
  goals: Goal[];
  today: string;
}) {
  function update(key: string, patch: Partial<ParamRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, i) => (
        <div
          key={row.key}
          className="flex flex-wrap items-end gap-3 rounded-lg border p-3"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`type-${row.key}`}>Thay đổi {i + 1}</Label>
            <select
              id={`type-${row.key}`}
              className={SELECT}
              value={row.type}
              onChange={(e) =>
                update(row.key, {
                  ...newRow(e.target.value as ParamType),
                  key: row.key,
                })
              }
            >
              {Object.entries(PARAM_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <ParamFields
            row={row}
            update={(p) => update(row.key, p)}
            categories={categories}
            goals={goals}
            today={today}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Xoá thay đổi ${i + 1}`}
            disabled={rows.length === 1}
            onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
          >
            <Trash2Icon />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        className="self-start"
        disabled={rows.length >= MAX_PARAMS}
        onClick={() => onChange([...rows, newRow()])}
      >
        <PlusIcon data-icon="inline-start" />
        Thêm thay đổi
      </Button>
    </div>
  );
}

function AmountHint({ text }: { text: string }) {
  const amount = parseAmountInput(text);
  return (
    <span className="text-xs text-muted-foreground">
      {amount !== null ? `= ${formatVND(amount)}` : "vd 2tr, 199k"}
    </span>
  );
}

function CategorySelect({
  id,
  value,
  categories,
  onChange,
}: {
  id: string;
  value: string;
  categories: Category[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      id={id}
      className={SELECT}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">— Chọn danh mục —</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {c.icon ? `${c.icon} ` : ""}
          {c.name}
        </option>
      ))}
    </select>
  );
}

function ParamFields({
  row,
  update,
  categories,
  goals,
  today,
}: {
  row: ParamRow;
  update: (patch: Partial<ParamRow>) => void;
  categories: Category[];
  goals: Goal[];
  today: string;
}) {
  const id = row.key;
  switch (row.type) {
    case "reduce_category":
      return (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`cat-${id}`}>Danh mục</Label>
            <CategorySelect
              id={`cat-${id}`}
              value={row.categoryId}
              categories={categories}
              onChange={(v) => update({ categoryId: v })}
            />
          </div>
          <div className="flex w-28 flex-col gap-1.5">
            <Label htmlFor={`pct-${id}`}>Giảm (%)</Label>
            <Input
              id={`pct-${id}`}
              type="number"
              min={1}
              max={100}
              step={1}
              value={row.percent}
              onChange={(e) => update({ percent: e.target.value })}
            />
          </div>
        </>
      );
    case "change_income":
      return (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`sign-${id}`}>Chiều</Label>
            <select
              id={`sign-${id}`}
              className={SELECT}
              value={row.incomeSign}
              onChange={(e) =>
                update({ incomeSign: e.target.value as "up" | "down" })
              }
            >
              <option value="up">Tăng</option>
              <option value="down">Giảm</option>
            </select>
          </div>
          <div className="flex w-40 flex-col gap-1.5">
            <Label htmlFor={`amt-${id}`}>Số tiền / tháng</Label>
            <Input
              id={`amt-${id}`}
              inputMode="decimal"
              value={row.amountText}
              placeholder="2tr"
              onChange={(e) => update({ amountText: e.target.value })}
            />
            <AmountHint text={row.amountText} />
          </div>
        </>
      );
    case "add_recurring_expense":
      return (
        <>
          <div className="flex w-44 flex-col gap-1.5">
            <Label htmlFor={`name-${id}`}>Tên khoản</Label>
            <Input
              id={`name-${id}`}
              value={row.name}
              maxLength={100}
              placeholder="Netflix"
              onChange={(e) => update({ name: e.target.value })}
            />
          </div>
          <div className="flex w-36 flex-col gap-1.5">
            <Label htmlFor={`amt-${id}`}>Số tiền / tháng</Label>
            <Input
              id={`amt-${id}`}
              inputMode="decimal"
              value={row.amountText}
              placeholder="199k"
              onChange={(e) => update({ amountText: e.target.value })}
            />
            <AmountHint text={row.amountText} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`cat-${id}`}>Danh mục</Label>
            <CategorySelect
              id={`cat-${id}`}
              value={row.categoryId}
              categories={categories}
              onChange={(v) => update({ categoryId: v })}
            />
          </div>
        </>
      );
    case "change_goal_deadline":
      return (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`goal-${id}`}>Mục tiêu</Label>
            <select
              id={`goal-${id}`}
              className={SELECT}
              value={row.goalId}
              onChange={(e) => update({ goalId: e.target.value })}
            >
              <option value="">— Chọn mục tiêu —</option>
              {goals.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`dl-${id}`}>Hạn mới</Label>
            <Input
              id={`dl-${id}`}
              type="date"
              min={today}
              value={row.deadline}
              onChange={(e) => update({ deadline: e.target.value })}
            />
          </div>
        </>
      );
  }
}
