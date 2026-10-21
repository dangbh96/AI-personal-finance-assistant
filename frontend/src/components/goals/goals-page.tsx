"use client";

import { PiggyBankIcon, PlusIcon, TargetIcon } from "lucide-react";
import { io } from "next/cache";
import { use, useState } from "react";

import { ContributionDialog } from "@/components/goals/contribution-dialog";
import { GoalCard } from "@/components/goals/goal-card";
import { GoalFormDialog } from "@/components/goals/goal-form-dialog";
import { PyfAllocationDialog } from "@/components/goals/pyf-allocation-dialog";
import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { Button } from "@/components/ui/button";
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
  withQuery,
  type Goal,
  type GoalList,
  type IncomeBrief,
  type PyfProposal,
  type PyfProposalRequest,
  type UnallocatedIncomeList,
} from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";

type FormState = { open: boolean; goal: Goal | null };

/**
 * `/goals`: mục tiêu tiết kiệm (thẻ tiến độ, tạo / sửa / tạm dừng, lịch sử góp) + "Phân bổ từ
 * thu nhập" cho các khoản thu chưa trích cho mục tiêu (Pay Yourself First).
 * `?today=YYYY-MM-DD` (tuỳ chọn) đặt "hôm nay" như các trang review.
 */
export function GoalsPage() {
  use(io());
  const today = useReviewToday();
  const goals = useApiData<GoalList>(withQuery("/goals", { today }));
  const incomes = useApiData<UnallocatedIncomeList>(
    withQuery("/goals/unallocated-incomes", { today }),
  );
  const [form, setForm] = useState<FormState>({ open: false, goal: null });
  const [contributing, setContributing] = useState<Goal | null>(null);
  const [proposal, setProposal] = useState<PyfProposal | null>(null);
  const [loadingIncome, setLoadingIncome] = useState<string | null>(null);
  const [incomeError, setIncomeError] = useState<string | null>(null);

  function reloadAll() {
    goals.reload();
    incomes.reload();
  }

  async function openAllocation(income: IncomeBrief) {
    setLoadingIncome(income.id);
    setIncomeError(null);
    try {
      const data = await apiRequest<PyfProposal>(
        "POST",
        withQuery("/goals/pyf-proposal", { today }),
        { income_transaction_id: income.id } satisfies PyfProposalRequest,
      );
      setProposal(data);
    } catch (err) {
      setIncomeError(describeError(err));
    } finally {
      setLoadingIncome(null);
    }
  }

  const items = goals.data?.items ?? [];
  const activeCount = items.filter((g) => g.status === "active").length;
  const unallocated = incomes.data?.items ?? [];
  const error = goals.error ?? incomes.error;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold">Mục tiêu tiết kiệm</h1>
          <p className="text-sm text-muted-foreground">
            Trả cho mình trước: khi nhận lương, trích tiền cho mục tiêu rồi mới chi tiêu.
          </p>
        </div>
        <Button onClick={() => setForm({ open: true, goal: null })}>
          <PlusIcon data-icon="inline-start" />
          Tạo mục tiêu
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error)}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card size="sm">
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <TargetIcon className="size-3.5" aria-hidden />
              Cần để dành mỗi tháng ({activeCount} mục tiêu đang thực hiện)
            </CardDescription>
            <CardTitle className="text-2xl tabular-nums">
              {goals.data ? formatVND(goals.data.total_suggested_monthly_saving) : "…"}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <PiggyBankIcon className="size-3.5" aria-hidden />
              Phân bổ từ thu nhập
            </CardDescription>
            <CardTitle className="text-base font-normal">
              {incomes.data
                ? unallocated.length > 0
                  ? `${unallocated.length} khoản thu chưa trích cho mục tiêu`
                  : "Không có khoản thu nào chờ phân bổ"
                : "Đang tải…"}
            </CardTitle>
          </CardHeader>
          {unallocated.length > 0 && (
            <CardContent>
              <ul className="flex flex-col gap-2 text-sm">
                {unallocated.slice(0, 5).map((income) => (
                  <li key={income.id} className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate">
                      {income.note || income.category_name} ·{" "}
                      <span className="tabular-nums">{formatVND(income.amount)}</span>
                      <span className="text-muted-foreground">
                        {" "}
                        · {formatDate(income.occurred_on)}
                      </span>
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openAllocation(income)}
                      disabled={loadingIncome !== null}
                    >
                      {loadingIncome === income.id ? "Đang tính…" : "Phân bổ"}
                    </Button>
                  </li>
                ))}
              </ul>
              {incomeError && (
                <p role="alert" className="mt-2 text-sm text-destructive">
                  {incomeError}
                </p>
              )}
            </CardContent>
          )}
        </Card>
      </div>

      {goals.data && items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
            <TargetIcon className="size-8 text-muted-foreground" aria-hidden />
            <p className="text-sm text-muted-foreground">
              Chưa có mục tiêu nào. Ví dụ: “Laptop 30 triệu trước tháng 3” — app sẽ tính mỗi
              tháng cần để dành bao nhiêu.
            </p>
            <Button onClick={() => setForm({ open: true, goal: null })}>
              <PlusIcon data-icon="inline-start" />
              Tạo mục tiêu đầu tiên
            </Button>
          </CardContent>
        </Card>
      ) : !goals.data ? (
        !error && <p className="text-sm text-muted-foreground">Đang tải…</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {items.map((goal) => (
            <GoalCard
              key={goal.id}
              goal={goal}
              today={today}
              onEdit={(g) => setForm({ open: true, goal: g })}
              onContribute={setContributing}
              onChanged={reloadAll}
            />
          ))}
        </div>
      )}

      <GoalFormDialog
        open={form.open}
        goal={form.goal}
        today={today}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        onSaved={reloadAll}
      />
      <ContributionDialog
        goal={contributing}
        today={today}
        onOpenChange={(open) => !open && setContributing(null)}
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
