"use client";

import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  type AdvisorSettings,
  type AdvisorSettingsUpdate,
} from "@/lib/api";
import { formatPercent, formatVND } from "@/lib/format";

const PATH = "/budget/advice/settings";

/** Hiển thị % từ tỉ lệ 0..1 mà không lộ sai số float (0.15 × 100 = 15.000000000000002). */
function toPercent(value: number): string {
  return String(Math.round(value * 10000) / 100);
}

function SettingsForm({
  settings,
  onSaved,
}: {
  settings: AdvisorSettings;
  onSaved: (settings: AdvisorSettings) => void;
}) {
  const [share, setShare] = useState(toPercent(settings.one_off_share_threshold));
  const [cv, setCv] = useState(toPercent(settings.stable_cv_threshold));
  const [months, setMonths] = useState(String(settings.min_history_months));
  const [step, setStep] = useState(String(settings.budget_rounding_step));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const body: AdvisorSettingsUpdate = {
        one_off_share_threshold: Number(share) / 100,
        stable_cv_threshold: Number(cv) / 100,
        min_history_months: Number(months),
        budget_rounding_step: Number(step),
      };
      const saved = await apiRequest<AdvisorSettings>("PATCH", PATH, body);
      onSaved(saved);
      setMessage("Đã lưu. Ngưỡng mới áp dụng khi tạo hoặc tính lại tư vấn.");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const fields = [
    {
      id: "one-off-share",
      label: "Khoản một lần khi chiếm ≥ (% phần vượt)",
      value: share,
      set: setShare,
      min: 1,
      max: 100,
      stepAttr: 1,
    },
    {
      id: "stable-cv",
      label: "Ổn định khi độ dao động CV ≤ (%)",
      value: cv,
      set: setCv,
      min: 1,
      max: 100,
      stepAttr: 0.5,
    },
    {
      id: "min-history",
      label: "Số tháng lịch sử tối thiểu",
      value: months,
      set: setMonths,
      min: 2,
      max: 12,
      stepAttr: 1,
    },
    {
      id: "rounding-step",
      label: "Làm tròn planned đề xuất tới (đồng)",
      value: step,
      set: setStep,
      min: 1000,
      max: 10_000_000,
      stepAttr: 1000,
    },
  ];

  return (
    <form onSubmit={save} className="flex flex-col gap-4 pt-3">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.id} className="flex flex-col gap-1.5">
            <Label htmlFor={`advisor-${f.id}`}>{f.label}</Label>
            <Input
              id={`advisor-${f.id}`}
              type="number"
              inputMode="decimal"
              min={f.min}
              max={f.max}
              step={f.stepAttr}
              required
              value={f.value}
              onChange={(e) => f.set(e.target.value)}
            />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving ? "Đang lưu…" : "Lưu ngưỡng"}
        </Button>
        {message && <p className="text-sm text-muted-foreground">{message}</p>}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}

/** Ngưỡng decision tree (`app_settings.budget_advisor`), ẩn trong mục thu gọn. */
export function AdvisorSettingsPanel() {
  const settings = useApiData<AdvisorSettings>(PATH);
  const [saved, setSaved] = useState<AdvisorSettings | null>(null);
  const current = saved ?? settings.data;

  return (
    <details className="group rounded-xl border bg-card px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium select-none">
        Ngưỡng phân loại
        {current && (
          <span className="ml-2 font-normal text-muted-foreground">
            khoản một lần ≥ {formatPercent(current.one_off_share_threshold * 100)} phần vượt · ổn
            định khi CV ≤ {formatPercent(current.stable_cv_threshold * 100)} · tối thiểu{" "}
            {current.min_history_months} tháng · làm tròn{" "}
            {formatVND(current.budget_rounding_step)}
          </span>
        )}
      </summary>
      {settings.error && !current && (
        <p role="alert" className="pt-3 text-destructive">
          {describeError(settings.error)}
        </p>
      )}
      {current && (
        <SettingsForm
          settings={current}
          onSaved={setSaved}
        />
      )}
    </details>
  );
}
