"use client";

import { ChevronLeftIcon, ChevronRightIcon, RefreshCwIcon } from "lucide-react";
import { io } from "next/cache";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useState } from "react";

import { HighlightList } from "@/components/reviews/highlight-list";
import { ReflectionForm } from "@/components/reviews/reflection-form";
import { ReviewMetricCards } from "@/components/reviews/review-metric-cards";
import { ReviewNarrative } from "@/components/reviews/review-narrative";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  type WeeklyReview,
  type WeeklyReviewGenerateRequest,
} from "@/lib/api";
import {
  addDays,
  formatWeekRange,
  isMonday,
  todayISO,
  weekStartOf,
} from "@/lib/dates";

const DATE_PATTERN = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

/** `?today=YYYY-MM-DD` đổi "hôm nay" (để thử tuần đang chạy / banner Thứ Hai). */
export function useReviewToday(): string {
  const param = useSearchParams().get("today");
  return param && DATE_PATTERN.test(param) ? param : todayISO();
}

function WeekNav({ week, today }: { week: string; today: string }) {
  const next = addDays(week, 7);
  const canNext = next <= weekStartOf(today);
  return (
    <div className="flex items-center gap-1">
      <Link
        href={`/reviews/weekly/${addDays(week, -7)}`}
        aria-label="Tuần trước"
        className={buttonVariants({ variant: "outline", size: "icon" })}
      >
        <ChevronLeftIcon />
      </Link>
      {canNext ? (
        <Link
          href={`/reviews/weekly/${next}`}
          aria-label="Tuần sau"
          className={buttonVariants({ variant: "outline", size: "icon" })}
        >
          <ChevronRightIcon />
        </Link>
      ) : (
        <Button variant="outline" size="icon" disabled aria-label="Tuần sau">
          <ChevronRightIcon />
        </Button>
      )}
    </div>
  );
}

/** `/reviews/weekly/[week]`: tạo on-demand, đọc narrative + số liệu, chia sẻ khi nhìn lại. */
export function WeeklyReviewPage({ week }: { week: string }) {
  use(io());
  const today = useReviewToday();
  const valid = DATE_PATTERN.test(week) && isMonday(week);
  const review = useApiData<WeeklyReview>(`/reviews/weekly/${week}`);
  const [generated, setGenerated] = useState<WeeklyReview | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!valid) {
    const monday = DATE_PATTERN.test(week) ? weekStartOf(week) : weekStartOf(today);
    return (
      <div className="flex flex-col gap-2">
        <h1 className="font-heading text-2xl font-semibold">Review tuần</h1>
        <p className="text-sm text-muted-foreground">
          Tuần được tính từ Thứ Hai.{" "}
          <Link
            href={`/reviews/weekly/${monday}`}
            className="text-foreground underline underline-offset-3"
          >
            Mở tuần {formatWeekRange(monday)}
          </Link>
        </p>
      </div>
    );
  }

  const notFound = review.error?.status === 404;
  const data =
    generated && generated.week_start === week ? generated : review.data?.week_start === week
      ? review.data
      : undefined;
  const notStarted = week > today;

  async function generate(regenerate: boolean) {
    setGenerating(true);
    setError(null);
    try {
      const body: WeeklyReviewGenerateRequest = { week_start: week, regenerate, today };
      setGenerated(await apiRequest<WeeklyReview>("POST", "/reviews/weekly", body));
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
            Review tuần {formatWeekRange(week)}
            {data && (
              <Badge variant={data.status === "completed" ? "secondary" : "outline"}>
                {data.status === "completed" ? "Đã nhìn lại" : "Chưa nhìn lại"}
              </Badge>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            Chuyện gì đã xảy ra → Vì sao → Điều đáng chú ý → Nhìn lại.{" "}
            <Link href="/reviews/weekly" className="underline underline-offset-3">
              Tất cả review
            </Link>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <Button
              variant="outline"
              onClick={() => setConfirmOpen(true)}
              disabled={generating}
            >
              <RefreshCwIcon />
              Tạo lại
            </Button>
          )}
          <WeekNav week={week} today={today} />
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
            <CardTitle>Chưa có review cho tuần này</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-start gap-3 text-sm text-muted-foreground">
            {notStarted ? (
              <p>Tuần này chưa bắt đầu.</p>
            ) : (
              <>
                <p>
                  App sẽ tổng hợp số liệu tuần, so với tuần trước, rồi nhờ AI diễn giải. Nếu AI
                  không dùng được, bạn vẫn nhận bản tóm tắt tự động.
                  {week === weekStartOf(today) && " Tuần đang chạy — số liệu tính đến hôm nay."}
                </p>
                <Button onClick={() => generate(false)} disabled={generating}>
                  {generating ? "Đang tạo review…" : "Tạo review tuần này"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <ReviewMetricCards metrics={data.metrics} />
          <ReviewNarrative narrative={data.narrative} model={data.model} />
          <HighlightList highlights={data.metrics.highlights} />
          <ReflectionForm
            key={data.id}
            kind="weekly"
            reviewId={data.id}
            question={data.narrative.reflection_question}
            reflections={data.reflections}
            from={data.week_start}
            to={data.week_end}
            markedIds={
              new Set(
                data.metrics.highlights.repeated_clusters.flatMap((c) => c.transaction_ids),
              )
            }
            markLabel="Lặp lại"
            onSaved={() => {
              setGenerated(null);
              review.reload();
            }}
          />
        </>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Tạo lại review tuần này?</AlertDialogTitle>
            <AlertDialogDescription>
              Số liệu và phần nhận xét sẽ được tính lại theo giao dịch hiện tại; review quay về
              trạng thái “Chưa nhìn lại”. Các chia sẻ đã lưu vẫn được giữ.
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
