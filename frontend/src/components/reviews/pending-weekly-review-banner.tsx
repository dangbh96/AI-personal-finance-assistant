"use client";

import { io } from "next/cache";
import Link from "next/link";
import { use } from "react";

import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { buttonVariants } from "@/components/ui/button";
import { useApiData } from "@/hooks/use-api-data";
import { withQuery, type PendingWeeklyReview } from "@/lib/api";
import { formatWeekRange, isMonday } from "@/lib/dates";

/** Thứ Hai: nhắc review tuần trước nếu chưa phản tư. Chỉ gợi ý, không tự tạo review. */
export function PendingWeeklyReviewBanner() {
  use(io());
  const today = useReviewToday();
  const monday = isMonday(today);
  // Backend cũng chỉ trả has_pending = true vào Thứ Hai; kiểm tra thêm ở đây cho rõ ý.
  const pending = useApiData<PendingWeeklyReview>(
    withQuery("/reviews/weekly/pending", { today }),
  );
  const data = pending.data;
  if (!monday || !data?.has_pending) return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <span>
        Có review tuần trước ({formatWeekRange(data.week_start)}) đang chờ bạn
        {data.review_status === "generated" ? " phản tư." : " nhìn lại."}
      </span>
      <Link
        href={`/reviews/weekly/${data.week_start}`}
        className={buttonVariants({ size: "sm" })}
      >
        {data.review_status === "generated" ? "Phản tư ngay" : "Xem review tuần"}
      </Link>
    </div>
  );
}
