"use client";

import { CopyIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiRequest, describeError, type Budget } from "@/lib/api";
import { monthToPeriod } from "@/lib/budget";
import { formatMonthLabel } from "@/lib/format";

/** CTA khi tháng chưa có ngân sách: tạo mới hoặc copy tháng trước. */
export function BudgetEmptyState({
  month,
  onCopied,
  compact = false,
}: {
  month: string;
  onCopied: (budget: Budget) => void;
  compact?: boolean;
}) {
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function copyPrevious() {
    setCopying(true);
    setError(null);
    try {
      onCopied(
        await apiRequest<Budget>("POST", "/budgets/copy-from-previous", {
          to_month: monthToPeriod(month),
        }),
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setCopying(false);
    }
  }

  return (
    <Card size={compact ? "sm" : "default"}>
      <CardHeader>
        <CardTitle>{formatMonthLabel(month)} chưa có ngân sách</CardTitle>
        <CardDescription>
          Lập kế hoạch chia thu nhập cho chi tiêu và tiết kiệm — chọn Hũ chi
          tiêu, 50/30/20 hoặc Trả cho mình trước.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/budget/new?month=${month}`}
            className={buttonVariants()}
          >
            <PlusIcon data-icon="inline-start" />
            Tạo budget tháng này
          </Link>
          <Button variant="outline" onClick={copyPrevious} disabled={copying}>
            <CopyIcon data-icon="inline-start" />
            {copying ? "Đang copy…" : "Copy tháng trước"}
          </Button>
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
