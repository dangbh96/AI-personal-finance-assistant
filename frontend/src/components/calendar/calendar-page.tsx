"use client";

import { io } from "next/cache";
import { use, useState } from "react";

import { CalendarMonthView } from "@/components/calendar/calendar-month-view";
import {
  ForecastLineChart,
  type ForecastDays,
} from "@/components/calendar/forecast-line-chart";
import { ForecastSettingsCard } from "@/components/calendar/forecast-settings-card";
import { RecurringFormDialog } from "@/components/calendar/recurring-form-dialog";
import { RecurringManager } from "@/components/calendar/recurring-manager";
import { RecurringSuggestionPanel } from "@/components/calendar/recurring-suggestion-panel";
import { UpcomingList } from "@/components/calendar/upcoming-list";
import { PyfAllocationDialog } from "@/components/goals/pyf-allocation-dialog";
import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { useApiData } from "@/hooks/use-api-data";
import {
  describeError,
  withQuery,
  type CalendarMonth,
  type Category,
  type ForecastOutput,
  type ForecastSettings,
  type PyfProposal,
  type RecurringList,
  type RecurringSuggestionList,
  type RecurringTransaction,
  type RecurringTransactionResult,
} from "@/lib/api";

type FormState = { open: boolean; item: RecurringTransaction | null };

/**
 * `/calendar`: lịch các khoản tiền (💰 🏠 💳 📱 🎯), khoản sắp đến hạn, dự báo số dư 30 / 60
 * ngày, khoản định kỳ (thủ công + phát hiện từ lịch sử). Mọi số do backend tính (deterministic).
 * `?today=YYYY-MM-DD` (tuỳ chọn) đặt "hôm nay" như các trang review / mục tiêu.
 */
export function CalendarPage() {
  use(io());
  const today = useReviewToday();
  const [month, setMonth] = useState(today.slice(0, 7));
  const [days, setDays] = useState<ForecastDays>(30);
  const [form, setForm] = useState<FormState>({ open: false, item: null });
  const [proposal, setProposal] = useState<PyfProposal | null>(null);

  const settings = useApiData<ForecastSettings>("/settings/forecast");
  const recurring = useApiData<RecurringList>(withQuery("/recurring-transactions", { today }));
  const calendar = useApiData<CalendarMonth>(
    withQuery("/calendar/month", { month: `${month}-01`, today }),
  );
  const forecast = useApiData<ForecastOutput>(withQuery("/forecast", { days, today }));
  const suggestions = useApiData<RecurringSuggestionList>(
    "/recurring-transactions/suggestions",
  );
  const categories = useApiData<Category[]>("/categories");

  function reloadAll() {
    recurring.reload();
    calendar.reload();
    forecast.reload();
    suggestions.reload();
  }

  function handleCreated(result: RecurringTransactionResult) {
    reloadAll();
    if (result.pyf_proposal) setProposal(result.pyf_proposal);
  }

  const error =
    settings.error ?? recurring.error ?? calendar.error ?? forecast.error ?? suggestions.error;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Lịch dòng tiền</h1>
        <p className="text-sm text-muted-foreground">
          Các khoản tiền sắp đến và số dư dự báo — để biết trước ngày nào có thể hụt tiền.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <ForecastLineChart
          forecast={forecast.data}
          days={days}
          onDaysChange={setDays}
          loading={forecast.loading}
        />
        <ForecastSettingsCard
          settings={settings.data}
          today={today}
          onSaved={() => {
            settings.reload();
            forecast.reload();
            calendar.reload();
          }}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <CalendarMonthView
          month={month}
          today={today}
          data={calendar.data}
          loading={calendar.loading}
          onMonthChange={setMonth}
        />
        <UpcomingList items={recurring.data?.items} today={today} onCreated={handleCreated} />
      </div>

      <RecurringManager
        items={recurring.data?.items}
        today={today}
        onAdd={() => setForm({ open: true, item: null })}
        onEdit={(item) => setForm({ open: true, item })}
        onChanged={reloadAll}
      />

      <RecurringSuggestionPanel data={suggestions.data} today={today} onChanged={reloadAll} />

      <RecurringFormDialog
        open={form.open}
        item={form.item}
        categories={categories.data ?? []}
        today={today}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        onSaved={reloadAll}
      />
      <PyfAllocationDialog
        proposal={proposal}
        today={today}
        onOpenChange={(open) => !open && setProposal(null)}
        onConfirmed={reloadAll}
      />
    </div>
  );
}
