"use client";

import {
  ArrowRightIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  RefreshCwIcon,
  SparklesIcon,
} from "lucide-react";
import { io } from "next/cache";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";

import { BudgetActualMiniTable } from "@/components/reviews/budget-actual-mini-table";
import { HighlightList } from "@/components/reviews/highlight-list";
import { IrregularItemsList } from "@/components/reviews/irregular-items-list";
import { MonthlySummaryCards } from "@/components/reviews/monthly-summary-cards";
import { ReflectionForm } from "@/components/reviews/reflection-form";
import { ReviewNarrative } from "@/components/reviews/review-narrative";
import { SpendingTypeChart } from "@/components/reviews/spending-type-chart";
import { WeeklyReflectionDigest } from "@/components/reviews/weekly-reflection-digest";
import { useReviewToday } from "@/components/reviews/weekly-review-page";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
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
  apiRequest,
  describeError,
  type BudgetAdviceGenerateRequest,
  type MonthlyReview,
  type MonthlyReviewGenerateRequest,
} from "@/lib/api";
import { shiftMonth, todayISO } from "@/lib/dates";
import { formatMonthLabel } from "@/lib/format";

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function MonthNav({ month, today }: { month: string; today: string }) {
  const next = shiftMonth(month, 1);
  const canNext = next <= today.slice(0, 7);
  return (
    <div className="flex items-center gap-1">
      <Link
        href={`/reviews/monthly/${shiftMonth(month, -1)}`}
        aria-label="Tháng trước"
        className={buttonVariants({ variant: "outline", size: "icon" })}
      >
        <ChevronLeftIcon />
      </Link>
      {canNext ? (
        <Link
          href={`/reviews/monthly/${next}`}
          aria-label="Tháng sau"
          className={buttonVariants({ variant: "outline", size: "icon" })}
        >
          <ChevronRightIcon />
        </Link>
      ) : (
        <Button variant="outline" size="icon" disabled aria-label="Tháng sau">
          <ChevronRightIcon />
        </Button>
      )}
    </div>
  );
}

/** CTA tạo tư vấn điều chỉnh ngân sách cho tháng (Phase 8) rồi chuyển sang `/budget/advice`. */
function BudgetAdviceCta({
  month,
  today,
  hasBudget,
  hasOverBudget,
}: {
  month: string;
  today: string;
  hasBudget: boolean;
  hasOverBudget: boolean;
}) {
  const router = useRouter();
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const todayQuery = today !== todayISO() ? `&today=${today}` : "";
  const adviceHref = `/budget/advice?month=${month}-01${todayQuery}`;

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      const body: BudgetAdviceGenerateRequest = { month: `${month}-01`, today };
      await apiRequest("POST", "/budget/advice/generate", body);
      router.push(adviceHref);
    } catch (err) {
      setError(describeError(err));
      setGenerating(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Chuẩn bị cho tháng tới</CardTitle>
        <CardDescription>
          {!hasBudget
            ? "Tháng này chưa có ngân sách đang theo dõi nên chưa có tư vấn điều chỉnh."
            : hasOverBudget
              ? "Có dòng ngân sách vượt kế hoạch. Phần tư vấn giúp bạn phân biệt: ngân sách đặt thấp, nhịp chi cần xem lại, hay chỉ là khoản một lần."
              : "Xem gợi ý điều chỉnh ngân sách dựa trên số liệu tháng này."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-start gap-3">
        <div className="flex flex-wrap gap-2">
          {hasBudget && (
            <Button
              onClick={generate}
              disabled={generating}
              variant={hasOverBudget ? "default" : "outline"}
            >
              <SparklesIcon />
              {generating ? "Đang tạo tư vấn…" : "Tạo tư vấn điều chỉnh"}
            </Button>
          )}
          <Link href={adviceHref} className={buttonVariants({ variant: "ghost" })}>
            Xem tư vấn đã có
            <ArrowRightIcon />
          </Link>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** `/reviews/monthly/[month]`: tạo on-demand, bức tranh tháng, narrative, phản tư tháng. */
export function MonthlyReviewPage({ month }: { month: string }) {
  use(io());
  const today = useReviewToday();
  const valid = MONTH_PATTERN.test(month);
  const review = useApiData<MonthlyReview>(`/reviews/monthly/${month}-01`);
  const [generated, setGenerated] = useState<MonthlyReview | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!valid) {
    const fallback = today.slice(0, 7);
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold">Review tháng</h1>
        <p className="text-sm text-muted-foreground">
          Tháng viết dạng YYYY-MM.{" "}
          <Link
            href={`/reviews/monthly/${fallback}`}
            className="text-foreground underline underline-offset-3"
          >
            Mở {formatMonthLabel(fallback).toLowerCase()}
          </Link>
        </p>
      </div>
    );
  }

  const monthStart = `${month}-01`;
  const notFound = review.error?.status === 404;
  const data =
    generated && generated.month === monthStart
      ? generated
      : review.data?.month === monthStart
        ? review.data
        : undefined;
  const notStarted = month > today.slice(0, 7);
  const isCurrent = month === today.slice(0, 7);

  async function generate(regenerate: boolean) {
    setGenerating(true);
    setError(null);
    try {
      const body: MonthlyReviewGenerateRequest = { month: monthStart, regenerate, today };
      setGenerated(await apiRequest<MonthlyReview>("POST", "/reviews/monthly", body));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setGenerating(false);
      setConfirmOpen(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex flex-wrap items-center gap-2 font-heading text-2xl font-semibold">
            Review {formatMonthLabel(month).toLowerCase()}
            {data && (
              <Badge variant={data.status === "completed" ? "secondary" : "outline"}>
                {data.status === "completed" ? "Đã phản tư" : "Chờ phản tư"}
              </Badge>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            Thu – Chi – Tiết kiệm, cơ cấu chi tiêu, ngân sách và những gì bạn ghi lại mỗi tuần.{" "}
            <Link href="/reviews/monthly" className="underline underline-offset-3">
              Tất cả review tháng
            </Link>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <Button variant="outline" onClick={() => setConfirmOpen(true)} disabled={generating}>
              <RefreshCwIcon />
              Tạo lại
            </Button>
          )}
          <MonthNav month={month} today={today} />
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {review.error && !notFound && !data && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(review.error)}
        </p>
      )}
      {!data && !review.error && review.loading && (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      )}

      {!data && notFound && (
        <Card>
          <CardHeader>
            <CardTitle>Chưa có review cho tháng này</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-3 text-sm text-muted-foreground">
            {notStarted ? (
              <p>Tháng này chưa bắt đầu.</p>
            ) : (
              <>
                <p>
                  App sẽ tổng hợp thu, chi, tiết kiệm, cơ cấu chi tiêu, so với tháng trước, đối
                  chiếu ngân sách và phản tư các tuần, rồi nhờ AI diễn giải. Nếu AI không dùng
                  được, bạn vẫn nhận bản tóm tắt tự động.
                  {isCurrent && " Tháng đang chạy — số liệu tính đến hôm nay."}
                </p>
                <Button onClick={() => generate(false)} disabled={generating}>
                  {generating ? "Đang tạo review…" : "Tạo review tháng"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <MonthlySummaryCards metrics={data.metrics} />
          <ReviewNarrative narrative={data.narrative} model={data.model} title="Nhìn lại tháng" />
          <SpendingTypeChart metrics={data.metrics} />
          <div className="grid gap-6 lg:grid-cols-2">
            <IrregularItemsList metrics={data.metrics} />
            <WeeklyReflectionDigest metrics={data.metrics} />
          </div>
          <BudgetActualMiniTable budget={data.metrics.budget} month={month} />
          <HighlightList highlights={data.metrics.highlights} />
          <ReflectionForm
            key={data.id}
            kind="monthly"
            reviewId={data.id}
            question={data.narrative.reflection_question}
            reflections={data.reflections}
            from={data.month}
            to={data.month_end}
            markedIds={new Set(data.metrics.irregular_items.map((t) => t.id))}
            markLabel="Bất thường"
            onSaved={(saved) => {
              // Cập nhật tại chỗ (không unmount form → giữ thông báo "Đã ghi nhận").
              setGenerated({
                ...data,
                status: "completed",
                reflections: [...data.reflections, saved],
              });
              review.reload();
            }}
          />
          <BudgetAdviceCta
            month={month}
            today={today}
            hasBudget={Boolean(data.metrics.budget)}
            hasOverBudget={(data.metrics.budget?.over_budget_count ?? 0) > 0}
          />
        </>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Tạo lại review tháng này?</AlertDialogTitle>
            <AlertDialogDescription>
              Số liệu và phần nhận xét sẽ được tính lại theo giao dịch, ngân sách và phản tư tuần
              hiện tại; review quay về trạng thái “Chờ phản tư”. Các câu trả lời phản tư đã lưu
              vẫn được giữ.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Huỷ</AlertDialogCancel>
            <AlertDialogAction onClick={() => generate(true)} disabled={generating}>
              {generating ? "Đang tạo…" : "Tạo lại"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
