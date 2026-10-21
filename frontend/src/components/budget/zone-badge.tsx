"use client";

import { AlertTriangleIcon } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { BudgetZone } from "@/lib/api";
import { formatVND } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  AUTO_ZONE_HINT,
  ZONE_CLASSES,
  ZONE_ICONS,
  ZONE_LABELS,
  ZONE_MODE_LABELS,
} from "@/lib/zones";

/** Badge 🟢/🟡/🔴 của một dòng (trạng thái do backend tính). */
export function ZoneBadge({ zone }: { zone: BudgetZone }) {
  const label = zone.zone ? (
    <>
      <span aria-hidden>{ZONE_ICONS[zone.zone]}</span>
      {ZONE_LABELS[zone.zone]}
    </>
  ) : (
    "Chưa tính vùng"
  );
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-4xl px-2 text-xs font-medium whitespace-nowrap",
        zone.zone ? ZONE_CLASSES[zone.zone] : "bg-muted text-muted-foreground",
      )}
    >
      {label}
    </span>
  );
}

/** Badge + tooltip giải thích ngưỡng (manual / auto từ lịch sử / % dự phòng) và pro-rata. */
export function ZoneTooltip({ zone }: { zone: BudgetZone }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            className="cursor-help rounded-4xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`Vùng linh hoạt: ${zone.zone ? ZONE_LABELS[zone.zone] : "chưa tính"}`}
            onClick={(e) => e.stopPropagation()}
          />
        }
      >
        <ZoneBadge zone={zone} />
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        className="flex max-w-sm flex-col items-start gap-1 text-left"
      >
        <ZoneExplanation zone={zone} />
      </TooltipContent>
    </Tooltip>
  );
}

function ZoneExplanation({ zone }: { zone: BudgetZone }) {
  const auto = zone.auto;
  return (
    <>
      <span className="font-medium">
        Vùng linh hoạt · {ZONE_MODE_LABELS[zone.zone_mode]}
      </span>
      {zone.calculated &&
      zone.comfort_low != null &&
      zone.comfort_high != null &&
      zone.warning_threshold != null ? (
        <>
          <span>
            🟢 Thoải mái: {formatVND(zone.comfort_low)} –{" "}
            {formatVND(zone.comfort_high)}
          </span>
          <span>
            🟡 Chú ý: tới {formatVND(zone.warning_threshold)} · 🔴 Cần xem lại:
            trên mức này
          </span>
        </>
      ) : (
        <span>
          Chưa tính ngưỡng cho dòng này — bấm “Tính vùng tự động” hoặc tự đặt
          ngưỡng.
        </span>
      )}
      <span>
        Thực tế {formatVND(zone.actual)} / kế hoạch {formatVND(zone.planned)}
      </span>
      {auto && (
        <span className="opacity-80">
          {auto.basis === "history"
            ? `${AUTO_ZONE_HINT} Dựa trên ${auto.history_months} tháng: trung bình ${formatVND(auto.mean ?? 0)}, độ lệch ${formatVND(auto.std ?? 0)}.`
            : auto.fallback_reason === "irregular_group"
              ? "Nhóm bất thường không có nhịp đều — dùng 87,5% / 112,5% / 125% kế hoạch."
              : `Chưa đủ ${auto.min_history_months} tháng dữ liệu — dùng 87,5% / 112,5% / 125% kế hoạch.`}
        </span>
      )}
      {auto?.stale && (
        <span className="font-medium">
          Dữ liệu đã thay đổi — tính lại sẽ cho vùng tới{" "}
          {formatVND(auto.suggested.comfort_high)}, cảnh báo trên{" "}
          {formatVND(auto.suggested.warning_threshold)}.
        </span>
      )}
      <span className="opacity-80">
        Theo nhịp tháng (pro-rata), tới hôm nay chi khoảng{" "}
        {formatVND(zone.expected_to_date)}.
      </span>
    </>
  );
}

/** Dòng phụ cảnh báo sớm theo pro-rata (không đổi zone chính). */
export function EarlyWarningLine({ zone }: { zone: BudgetZone }) {
  if (!zone.early_warning || !zone.early_warning_message) return null;
  return (
    <span className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300">
      <AlertTriangleIcon className="size-3.5 shrink-0" />
      {zone.early_warning_message}
    </span>
  );
}
