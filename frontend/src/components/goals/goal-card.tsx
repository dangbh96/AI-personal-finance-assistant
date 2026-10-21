"use client";

import {
  CalendarIcon,
  HistoryIcon,
  PauseIcon,
  PencilIcon,
  PlayIcon,
  PlusIcon,
  Trash2Icon,
} from "lucide-react";
import { useState } from "react";

import { ContributionTimeline } from "@/components/goals/contribution-timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  apiRequest,
  describeError,
  withQuery,
  type Goal,
  type GoalStatus,
  type GoalUpdate,
} from "@/lib/api";
import { formatDate, formatPercent, formatVND } from "@/lib/format";
import {
  BEHIND_TONE,
  GOAL_STATUS_LABELS,
  GOAL_STATUS_TONES,
  ON_TRACK_TONE,
  describeMonthsRemaining,
} from "@/lib/goals";
import { cn } from "@/lib/utils";

/** Thẻ mục tiêu: tiến độ, còn thiếu, hạn, gợi ý mỗi tháng (mọi số từ backend) + thao tác. */
export function GoalCard({
  goal,
  today,
  onEdit,
  onContribute,
  onChanged,
}: {
  goal: Goal;
  today: string;
  onEdit: (goal: Goal) => void;
  onContribute: (goal: Goal) => void;
  onChanged: () => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(status: GoalStatus) {
    setBusy(true);
    setError(null);
    try {
      await apiRequest<Goal>("PATCH", withQuery(`/goals/${goal.id}`, { today }), {
        status,
      } satisfies GoalUpdate);
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Xoá mục tiêu “${goal.name}”? Lịch sử khoản góp cũng bị xoá.`)) return;
    setBusy(true);
    setError(null);
    try {
      await apiRequest<void>("DELETE", `/goals/${goal.id}`);
      onChanged();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  }

  const active = goal.status === "active";

  return (
    <Card className={cn(goal.status === "paused" && "opacity-80")}>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <span className="truncate">{goal.name}</span>
          <Badge variant="outline" className={GOAL_STATUS_TONES[goal.status]}>
            {GOAL_STATUS_LABELS[goal.status]}
          </Badge>
          {active && (
            <Badge variant="outline" className={goal.on_track ? ON_TRACK_TONE : BEHIND_TONE}>
              {goal.on_track ? "Đúng tiến độ" : "Chậm tiến độ"}
            </Badge>
          )}
        </CardTitle>
        <CardDescription className="flex items-center gap-1.5">
          <CalendarIcon className="size-3.5" aria-hidden />
          Hạn {formatDate(goal.deadline)} ·{" "}
          {describeMonthsRemaining(goal.months_remaining, goal.overdue)} · Ưu tiên{" "}
          {goal.priority}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <div
            className="h-2.5 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label={`Tiến độ ${goal.name}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={goal.progress_pct}
          >
            <div
              className={cn(
                "h-full rounded-full",
                goal.status === "achieved"
                  ? "bg-emerald-500"
                  : goal.on_track
                    ? "bg-sky-500"
                    : "bg-amber-500",
              )}
              style={{ width: `${goal.progress_pct}%` }}
            />
          </div>
          <p className="flex justify-between text-sm tabular-nums">
            <span>
              <strong>{formatVND(goal.current_amount)}</strong>
              <span className="text-muted-foreground"> / {formatVND(goal.target_amount)}</span>
            </span>
            <span className="text-muted-foreground">{formatPercent(goal.progress_pct)}</span>
          </p>
        </div>
        {goal.remaining_amount > 0 ? (
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm tabular-nums">
            <dt className="text-muted-foreground">Còn thiếu</dt>
            <dd className="text-right">{formatVND(goal.remaining_amount)}</dd>
            <dt className="text-muted-foreground">
              {goal.overdue ? "Cần bổ sung" : "Gợi ý để dành / tháng"}
            </dt>
            <dd className="text-right font-medium">
              {formatVND(goal.suggested_monthly_saving)}
            </dd>
          </dl>
        ) : (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">
            Đã đủ số tiền mục tiêu 🎉
          </p>
        )}
        {showHistory && (
          <ContributionTimeline
            goalId={goal.id}
            today={today}
            version={goal.contribution_count}
            onChanged={onChanged}
          />
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        {active && (
          <Button size="sm" onClick={() => onContribute(goal)} disabled={busy}>
            <PlusIcon data-icon="inline-start" />
            Thêm khoản góp
          </Button>
        )}
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowHistory((v) => !v)}
          aria-expanded={showHistory}
        >
          <HistoryIcon data-icon="inline-start" />
          Lịch sử ({goal.contribution_count})
        </Button>
        <Button size="sm" variant="outline" onClick={() => onEdit(goal)} disabled={busy}>
          <PencilIcon data-icon="inline-start" />
          Sửa
        </Button>
        {active && (
          <Button size="sm" variant="outline" onClick={() => setStatus("paused")} disabled={busy}>
            <PauseIcon data-icon="inline-start" />
            Tạm dừng
          </Button>
        )}
        {goal.status === "paused" && (
          <Button size="sm" variant="outline" onClick={() => setStatus("active")} disabled={busy}>
            <PlayIcon data-icon="inline-start" />
            Tiếp tục
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          onClick={remove}
          disabled={busy}
          title="Xoá được khi chưa có khoản góp hoặc đã tạm dừng"
        >
          <Trash2Icon data-icon="inline-start" />
          Xoá
        </Button>
      </CardFooter>
    </Card>
  );
}
