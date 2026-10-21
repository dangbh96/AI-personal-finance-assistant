"use client";

import { SlidersHorizontalIcon } from "lucide-react";
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
  type BudgetAllocation,
  type BudgetZone,
  type ZoneMode,
  type ZoneUpdate,
} from "@/lib/api";
import { parseBudgetAmount } from "@/lib/budget";
import { formatAmountPlain, formatVND } from "@/lib/format";
import { AUTO_ZONE_HINT, ZONE_MODE_LABELS } from "@/lib/zones";

type ManualField = "comfort_low" | "comfort_high" | "warning_threshold";

const FIELDS: { key: ManualField; label: string; hint: string }[] = [
  {
    key: "comfort_low",
    label: "Mức dưới vùng thoải mái",
    hint: "Chi dưới mức này vẫn là bình thường",
  },
  {
    key: "comfort_high",
    label: "Mức trên vùng thoải mái",
    hint: "Vượt mức này → 🟡 chú ý",
  },
  {
    key: "warning_threshold",
    label: "Ngưỡng cảnh báo",
    hint: "Vượt mức này → 🔴 cần xem lại",
  },
];

/**
 * Nút "Chỉnh vùng" + dialog chọn Auto / Thủ công. Thủ công: kiểm tra ngay trên client
 * `mức dưới <= mức trên <= ngưỡng cảnh báo` (backend kiểm lại). Auto: backend tính ngưỡng.
 */
export function ZoneSettingsDialog({
  zone,
  disabled,
  onSaved,
}: {
  zone: BudgetZone;
  disabled?: boolean;
  onSaved: (allocation: BudgetAllocation) => void;
}) {
  const [open, setOpen] = useState(false);
  // Dialog nằm trong dòng bảng có thể bấm (drill-down): chặn click (kể cả từ portal) nổi lên dòng.
  return (
    <span className="contents" onClick={(e) => e.stopPropagation()}>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`Chỉnh vùng linh hoạt: ${zone.label}`}
        title={disabled ? "Ngân sách đã đóng — mở lại để chỉnh vùng" : "Chỉnh vùng"}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <SlidersHorizontalIcon />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Vùng linh hoạt · {zone.label}</DialogTitle>
            <DialogDescription>
              Kế hoạch (target): {formatVND(zone.planned)}. Vùng giúp phân biệt
              chi hơi cao một chút với khoản thật sự cần xem lại.
            </DialogDescription>
          </DialogHeader>
          {open && (
            <ZoneForm
              zone={zone}
              onCancel={() => setOpen(false)}
              onSaved={(allocation) => {
                setOpen(false);
                onSaved(allocation);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </span>
  );
}

function initialValues(zone: BudgetZone): Record<ManualField, string> {
  const source =
    zone.calculated && zone.comfort_low != null
      ? zone
      : (zone.auto?.suggested ?? null);
  const value = (n: number | null | undefined) =>
    n == null ? "" : formatAmountPlain(n);
  return {
    comfort_low: value(source?.comfort_low),
    comfort_high: value(source?.comfort_high),
    warning_threshold: value(source?.warning_threshold),
  };
}

/** Kiểm tra trên client → body PATCH hoặc thông báo lỗi. */
function validateManual(
  values: Record<ManualField, string>,
): { error: string } | { body: ZoneUpdate } {
  const parsed = {} as Record<ManualField, number>;
  for (const field of FIELDS) {
    const amount = parseBudgetAmount(values[field.key]);
    if (amount === null) return { error: `Nhập số tiền hợp lệ cho “${field.label}”` };
    parsed[field.key] = amount;
  }
  if (parsed.comfort_low > parsed.comfort_high) {
    return { error: "Mức dưới vùng thoải mái phải nhỏ hơn hoặc bằng mức trên" };
  }
  if (parsed.comfort_high > parsed.warning_threshold) {
    return { error: "Mức trên vùng thoải mái phải nhỏ hơn hoặc bằng ngưỡng cảnh báo" };
  }
  return { body: { zone_mode: "manual", ...parsed } };
}

function ZoneForm({
  zone,
  onCancel,
  onSaved,
}: {
  zone: BudgetZone;
  onCancel: () => void;
  onSaved: (allocation: BudgetAllocation) => void;
}) {
  const [mode, setMode] = useState<ZoneMode>(zone.zone_mode);
  const [values, setValues] = useState(() => initialValues(zone));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    let body: ZoneUpdate = { zone_mode: "auto" };
    if (mode === "manual") {
      const result = validateManual(values);
      if ("error" in result) {
        setError(result.error);
        return;
      }
      body = result.body;
    }
    setSaving(true);
    try {
      const allocation = await apiRequest<BudgetAllocation>(
        "PATCH",
        `/budget-allocations/${zone.allocation_id}/zone`,
        body,
      );
      onSaved(allocation);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Cách đặt ngưỡng</legend>
        {(["auto", "manual"] as const).map((value) => (
          <label key={value} className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="zone_mode"
              className="mt-0.5 size-4 accent-primary"
              checked={mode === value}
              onChange={() => {
                setMode(value);
                setError(null);
              }}
            />
            <span className="flex flex-col">
              <span className="font-medium">{ZONE_MODE_LABELS[value]}</span>
              <span className="text-xs text-muted-foreground">
                {value === "auto"
                  ? `${AUTO_ZONE_HINT} Thiếu dữ liệu thì dùng 87,5% / 112,5% / 125% kế hoạch.`
                  : "Bạn tự đặt vùng thoải mái và ngưỡng cảnh báo."}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      {mode === "auto" && zone.auto && (
        <p className="rounded-lg bg-muted px-3 py-2 text-sm">
          Ngưỡng tính từ dữ liệu hiện tại: thoải mái{" "}
          {formatVND(zone.auto.suggested.comfort_low)} –{" "}
          {formatVND(zone.auto.suggested.comfort_high)}, cảnh báo trên{" "}
          {formatVND(zone.auto.suggested.warning_threshold)}.
        </p>
      )}

      {mode === "manual" && (
        <div className="flex flex-col gap-3">
          {FIELDS.map((field) => (
            <div key={field.key} className="flex flex-col gap-1.5">
              <Label htmlFor={`zone-${field.key}`}>{field.label}</Label>
              <Input
                id={`zone-${field.key}`}
                inputMode="numeric"
                placeholder="vd. 4tr5"
                value={values[field.key]}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [field.key]: e.target.value }))
                }
              />
              <span className="text-xs text-muted-foreground">{field.hint}</span>
            </div>
          ))}
        </div>
      )}

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
          {saving ? "Đang lưu…" : "Lưu vùng"}
        </Button>
      </DialogFooter>
    </form>
  );
}
