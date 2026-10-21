"use client";

import { ChevronLeftIcon, ChevronRightIcon, RefreshCwIcon, SparklesIcon } from "lucide-react";
import { io } from "next/cache";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";

import { AdvisorSettingsPanel } from "@/components/budget-advice/advisor-settings-panel";
import { BudgetAdviceList } from "@/components/budget-advice/budget-advice-list";
import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import {
  ApiError,
  apiRequest,
  describeError,
  withQuery,
  type BudgetAdviceGenerateRequest,
  type BudgetAdviceList as BudgetAdviceListData,
} from "@/lib/api";
import {
  ADVICE_STATUS_FILTER_LABELS,
  ADVICE_STATUS_FILTERS,
  isAdviceStatusFilter,
  type AdviceStatusFilter,
} from "@/lib/advice";
import { shiftMonth } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const MONTH_PARAM = /^(\d{4}-(0[1-9]|1[0-2]))(-01)?$/;
const NO_BUDGET_CODES = new Set(["budget_not_found", "budget_not_active"]);

/**
 * `/budget/advice?month=YYYY-MM-01&status=open`: tư vấn điều chỉnh ngân sách của một tháng.
 * Verdict + evidence do backend tính; AI chỉ diễn giải. Accept luôn qua hộp xác nhận.
 */
export function BudgetAdvicePage() {
  use(io());
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const today = useReviewToday();
  const currentYm = today.slice(0, 7);
  const ym = MONTH_PARAM.exec(params.get("month") ?? "")?.[1] ?? shiftMonth(currentYm, -1);
  const statusParam = params.get("status");
  const filter: AdviceStatusFilter = isAdviceStatusFilter(statusParam) ? statusParam : "open";

  const list = useApiData<BudgetAdviceListData>(withQuery("/budget/advice", { month: `${ym}-01` }));
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<{ code: string | null; text: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const items = list.data?.items.filter((a) => a.month === `${ym}-01`) ?? [];
  const counts = Object.fromEntries(
    ADVICE_STATUS_FILTERS.map((s) => [
      s,
      s === "all" ? items.length : items.filter((a) => a.status === s).length,
    ]),
  ) as Record<AdviceStatusFilter, number>;
  const notStarted = ym > currentYm;

  function navigate(changes: Record<string, string>) {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(changes)) next.set(key, value);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  function changeMonth(next: string) {
    setError(null);
    setMessage(null);
    navigate({ month: `${next}-01` });
  }

  async function generate(regenerate: boolean) {
    setGenerating(true);
    setError(null);
    setMessage(null);
    try {
      const body: BudgetAdviceGenerateRequest = { month: `${ym}-01`, regenerate, today };
      await apiRequest("POST", "/budget/advice/generate", body);
      list.reload();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      setError({ code, text: describeError(err) });
    } finally {
      setGenerating(false);
    }
  }

  function changed(text: string | null) {
    setMessage(text);
    list.reload();
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Tư vấn điều chỉnh ngân sách</h1>
          <p className="text-sm text-muted-foreground">
            {formatMonthLabel(ym)} · với mỗi dòng ngân sách, app phân biệt: ngân sách đặt thấp,
            nhịp chi cần xem lại, hay chỉ là khoản một lần — kèm số liệu để bạn quyết định.
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng trước"
            onClick={() => changeMonth(shiftMonth(ym, -1))}
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="outline"
            size="icon"
            aria-label="Tháng sau"
            disabled={shiftMonth(ym, 1) > currentYm}
            onClick={() => changeMonth(shiftMonth(ym, 1))}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {items.length > 0 ? (
          <Button
            variant="outline"
            onClick={() => generate(true)}
            disabled={generating || notStarted}
          >
            <RefreshCwIcon />
            {generating ? "Đang tính lại…" : "Tính lại tư vấn đang chờ"}
          </Button>
        ) : (
          <Button onClick={() => generate(false)} disabled={generating || notStarted || list.loading}>
            <SparklesIcon />
            {generating ? "Đang tạo tư vấn…" : "Tạo tư vấn điều chỉnh"}
          </Button>
        )}
        <Link
          href={`/reviews/monthly/${ym}`}
          className={buttonVariants({ variant: "ghost" })}
        >
          Review {formatMonthLabel(ym).toLowerCase()}
        </Link>
        <Link
          href={`/budget?month=${ym}&tab=track`}
          className={buttonVariants({ variant: "ghost" })}
        >
          Ngân sách {formatMonthLabel(ym).toLowerCase()}
        </Link>
      </div>

      {message && (
        <p role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
          {message}
        </p>
      )}
      {error && (
        <Card>
          <CardHeader>
            <CardTitle>
              {error.code && NO_BUDGET_CODES.has(error.code)
                ? "Chưa có ngân sách đang theo dõi"
                : "Chưa tạo được tư vấn"}
            </CardTitle>
            <CardDescription role="alert">{error.text}</CardDescription>
          </CardHeader>
          {error.code && NO_BUDGET_CODES.has(error.code) && (
            <CardContent>
              <Link
                href={`/budget?month=${ym}`}
                className={buttonVariants({ variant: "outline" })}
              >
                Mở ngân sách {formatMonthLabel(ym).toLowerCase()}
              </Link>
            </CardContent>
          )}
        </Card>
      )}
      {list.error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(list.error)}
        </p>
      )}
      {list.loading && !list.data && (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      )}

      {list.data && items.length === 0 && !error && (
        <Card>
          <CardHeader>
            <CardTitle>Chưa có tư vấn cho {formatMonthLabel(ym).toLowerCase()}</CardTitle>
            <CardDescription>
              {notStarted
                ? "Tháng này chưa bắt đầu."
                : "App sẽ so sánh thực chi với kế hoạch của từng dòng ngân sách, xem lại 3 tháng gần nhất và các giao dịch bất thường, rồi nhờ AI diễn giải. Ngân sách chỉ thay đổi khi bạn xác nhận."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {items.length > 0 && (
        <>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Lọc theo trạng thái">
            {ADVICE_STATUS_FILTERS.map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={filter === s}
                onClick={() => navigate({ status: s })}
                className={cn(
                  "rounded-4xl border px-3 py-1 text-sm transition-colors",
                  filter === s
                    ? "border-primary bg-primary text-primary-foreground"
                    : "hover:bg-muted",
                )}
              >
                {ADVICE_STATUS_FILTER_LABELS[s]} ({counts[s]})
              </button>
            ))}
          </div>
          <BudgetAdviceList items={items} filter={filter} onChanged={changed} />
        </>
      )}

      <AdvisorSettingsPanel />
    </div>
  );
}
