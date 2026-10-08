"use client";

import { ChevronLeftIcon, ChevronRightIcon, SearchIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Category, Direction, SpendingType } from "@/lib/api";
import { shiftMonth } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";
import { DIRECTION_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";

export type Filters = {
  month: string;
  categoryId: string | null;
  spendingType: SpendingType | null;
  direction: Direction | null;
  q: string;
};

const ALL = "__all__";

function FilterSelect({
  label,
  value,
  items,
  onChange,
}: {
  label: string;
  value: string | null;
  items: Record<string, string>;
  onChange: (value: string | null) => void;
}) {
  const withAll = { [ALL]: `${label}: tất cả`, ...items };
  return (
    <Select
      items={withAll}
      value={value ?? ALL}
      onValueChange={(v) => onChange(v === ALL || v === null ? null : String(v))}
    >
      <SelectTrigger aria-label={label} className="min-w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{withAll[ALL]}</SelectItem>
        <SelectSeparator />
        {Object.entries(items).map(([v, text]) => (
          <SelectItem key={v} value={v}>
            {text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function TransactionFilters({
  filters,
  categories,
  searchText,
  onSearchTextChange,
  onChange,
}: {
  filters: Filters;
  categories: Category[];
  searchText: string;
  onSearchTextChange: (text: string) => void;
  onChange: (patch: Partial<Filters>) => void;
}) {
  const categoryItems = Object.fromEntries(
    categories
      .filter((c) => !filters.direction || c.kind === filters.direction)
      .map((c) => [c.id, `${c.icon ?? ""} ${c.name}`.trim()]),
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          aria-label="Tháng trước"
          onClick={() => onChange({ month: shiftMonth(filters.month, -1) })}
        >
          <ChevronLeftIcon />
        </Button>
        <Input
          type="month"
          aria-label="Chọn tháng"
          title={formatMonthLabel(filters.month)}
          className="w-40"
          value={filters.month}
          onChange={(e) => e.target.value && onChange({ month: e.target.value })}
        />
        <Button
          variant="outline"
          size="icon"
          aria-label="Tháng sau"
          onClick={() => onChange({ month: shiftMonth(filters.month, 1) })}
        >
          <ChevronRightIcon />
        </Button>
      </div>

      <FilterSelect
        label="Thu/Chi"
        value={filters.direction}
        items={DIRECTION_LABELS}
        onChange={(v) =>
          onChange({
            direction: v as Direction | null,
            categoryId: null,
            spendingType: v === "income" ? null : filters.spendingType,
          })
        }
      />
      <FilterSelect
        label="Danh mục"
        value={filters.categoryId}
        items={categoryItems}
        onChange={(v) => onChange({ categoryId: v })}
      />
      {filters.direction !== "income" && (
        <FilterSelect
          label="Loại chi tiêu"
          value={filters.spendingType}
          items={SPENDING_TYPE_LABELS}
          onChange={(v) => onChange({ spendingType: v as SpendingType | null })}
        />
      )}

      <div className="relative min-w-48 flex-1">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          aria-label="Tìm trong ghi chú"
          placeholder="Tìm trong ghi chú…"
          className="pl-8"
          maxLength={100}
          value={searchText}
          onChange={(e) => onSearchTextChange(e.target.value)}
        />
      </div>
    </div>
  );
}
