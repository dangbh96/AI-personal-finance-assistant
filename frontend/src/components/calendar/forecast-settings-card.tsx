"use client";

import { WalletIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  apiRequest,
  describeError,
  withQuery,
  type ForecastSettings,
  type ForecastSettingsUpdate,
} from "@/lib/api";
import { parseAmountInput } from "@/lib/amount";
import { parseBalanceInput } from "@/lib/calendar";
import { formatAmountPlain, formatDate, formatVND } from "@/lib/format";

function balanceText(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "";
  return `${amount < 0 ? "-" : ""}${formatAmountPlain(Math.abs(amount))}`;
}

/**
 * Số dư đầu (giả định của dự báo — app không kết nối ngân hàng), ngày tính số dư, ngưỡng cảnh
 * báo và ngày để dành mục tiêu. Lưu qua `PATCH /settings/forecast`.
 */
export function ForecastSettingsCard({
  settings,
  today,
  onSaved,
}: {
  settings: ForecastSettings | undefined;
  today: string;
  onSaved: (settings: ForecastSettings) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <WalletIcon className="size-4" aria-hidden />
          Số dư & cảnh báo
        </CardTitle>
        <CardDescription>
          Số dư do bạn tự nhập — đây là giả định để dự báo, app không đọc số dư ngân hàng.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {settings ? (
          <SettingsForm
            key={JSON.stringify(settings)}
            settings={settings}
            today={today}
            onSaved={onSaved}
          />
        ) : (
          <p className="text-sm text-muted-foreground">Đang tải…</p>
        )}
      </CardContent>
    </Card>
  );
}

function SettingsForm({
  settings,
  today,
  onSaved,
}: {
  settings: ForecastSettings;
  today: string;
  onSaved: (settings: ForecastSettings) => void;
}) {
  const [balanceInput, setBalanceInput] = useState(balanceText(settings.starting_balance));
  const [balanceOn, setBalanceOn] = useState(settings.starting_balance_on ?? today);
  const [thresholdInput, setThresholdInput] = useState(
    formatAmountPlain(settings.low_balance_threshold),
  );
  const [goalDay, setGoalDay] = useState(String(settings.goal_saving_day_of_month));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasBalance = balanceInput.trim() !== "";
  const balance = hasBalance ? parseBalanceInput(balanceInput, parseAmountInput) : null;
  const threshold = parseBalanceInput(thresholdInput, parseAmountInput);
  const goalDayValue = Number(goalDay);
  const errors = {
    balance: hasBalance && balance === null ? "Số dư không hợp lệ (vd 12tr, -500k, 0)" : null,
    threshold: threshold === null || threshold < 0 ? "Ngưỡng phải là số tiền ≥ 0" : null,
    goalDay:
      Number.isInteger(goalDayValue) && goalDayValue >= 1 && goalDayValue <= 31
        ? null
        : "Ngày từ 1 tới 31",
    balanceOn: hasBalance && !balanceOn ? "Chọn ngày" : null,
  };
  const valid = !errors.balance && !errors.threshold && !errors.goalDay && !errors.balanceOn;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || threshold === null) return;
    setSaving(true);
    setError(null);
    try {
      const body: ForecastSettingsUpdate = {
        starting_balance: balance,
        low_balance_threshold: threshold,
        goal_saving_day_of_month: goalDayValue,
      };
      if (balance !== null) body.starting_balance_on = balanceOn;
      const result = await apiRequest<ForecastSettings>(
        "PATCH",
        withQuery("/settings/forecast", { today }),
        body,
      );
      onSaved(result);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const hint = (message: string | null, fallback: string) => (
    <p className={message ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
      {message ?? fallback}
    </p>
  );

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fc-balance">Số dư hiện có</Label>
          <Input
            id="fc-balance"
            inputMode="decimal"
            autoComplete="off"
            placeholder="12tr"
            value={balanceInput}
            onChange={(e) => setBalanceInput(e.target.value)}
            aria-invalid={!!errors.balance}
          />
          {hint(
            errors.balance,
            balance !== null ? `= ${formatVND(balance)}` : "Chưa nhập — dự báo tính từ 0 ₫",
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fc-balance-on">Tính tại đầu ngày</Label>
          <Input
            id="fc-balance-on"
            type="date"
            value={balanceOn}
            onChange={(e) => setBalanceOn(e.target.value)}
            aria-invalid={!!errors.balanceOn}
          />
          {hint(errors.balanceOn, "Giao dịch từ ngày này trở đi được cộng / trừ vào.")}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fc-threshold">Cảnh báo khi số dư dưới</Label>
          <Input
            id="fc-threshold"
            inputMode="decimal"
            autoComplete="off"
            placeholder="1tr"
            value={thresholdInput}
            onChange={(e) => setThresholdInput(e.target.value)}
            aria-invalid={!!errors.threshold}
          />
          {hint(errors.threshold, threshold !== null ? `= ${formatVND(threshold)}` : "")}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fc-goal-day">Ngày để dành mục tiêu 🎯</Label>
          <Input
            id="fc-goal-day"
            type="number"
            min={1}
            max={31}
            value={goalDay}
            onChange={(e) => setGoalDay(e.target.value)}
            aria-invalid={!!errors.goalDay}
          />
          {hint(errors.goalDay, "31 → ngày cuối ở tháng ngắn")}
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground" role="status">
          {settings.starting_balance !== null && settings.starting_balance !== undefined
            ? `Đang dùng ${formatVND(settings.starting_balance)}${
                settings.starting_balance_on
                  ? ` tại ${formatDate(settings.starting_balance_on)}`
                  : ""
              }.`
            : "Chưa có số dư."}
        </p>
        <Button type="submit" size="sm" disabled={saving || !valid}>
          {saving ? "Đang lưu…" : "Lưu"}
        </Button>
      </div>
    </form>
  );
}
