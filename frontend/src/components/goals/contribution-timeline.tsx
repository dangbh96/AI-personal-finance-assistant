"use client";

import { Trash2Icon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  withQuery,
  type GoalDetail,
} from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";

/** Lịch sử khoản góp của một mục tiêu (mới nhất trước), có nguồn thu nhập nếu từ PYF. */
export function ContributionTimeline({
  goalId,
  today,
  version,
  onChanged,
}: {
  goalId: string;
  today: string;
  /** Đổi giá trị để tải lại (vd sau khi thêm khoản góp). */
  version: number;
  onChanged: () => void;
}) {
  const detail = useApiData<GoalDetail>(
    withQuery(`/goals/${goalId}`, { today, v: version }),
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function remove(contributionId: string) {
    if (!window.confirm("Xoá khoản góp này? Tiến độ mục tiêu sẽ giảm tương ứng.")) return;
    setDeleting(contributionId);
    setError(null);
    try {
      await apiRequest<void>("DELETE", `/goals/${goalId}/contributions/${contributionId}`);
      detail.reload();
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setDeleting(null);
    }
  }

  if (detail.error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {describeError(detail.error)}
      </p>
    );
  }
  if (!detail.data) {
    return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  }
  const items = detail.data.contributions;
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Chưa có khoản góp nào.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <ol className="flex flex-col gap-2 border-l pl-4" aria-label="Lịch sử khoản góp">
        {items.map((c) => (
          <li key={c.id} className="relative flex items-start justify-between gap-2 text-sm">
            <span
              className="absolute top-1.5 -left-[1.3rem] size-2 rounded-full bg-emerald-500"
              aria-hidden
            />
            <div className="min-w-0">
              <p>
                <span className="font-medium tabular-nums">{formatVND(c.amount)}</span>
                <span className="text-muted-foreground"> · {formatDate(c.contributed_on)}</span>
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {c.income_transaction
                  ? `Từ thu nhập: ${c.income_transaction.note || c.income_transaction.category_name} ${formatVND(c.income_transaction.amount)} (${formatDate(c.income_transaction.occurred_on)})`
                  : "Góp thủ công"}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Xoá khoản góp"
              title="Xoá khoản góp"
              disabled={deleting === c.id}
              onClick={() => remove(c.id)}
            >
              <Trash2Icon />
            </Button>
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
