import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { BudgetWizard } from "@/components/budget/budget-wizard";

export const metadata: Metadata = { title: "Tạo ngân sách — Personal CFO" };

export default function NewBudgetPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Tạo ngân sách</h1>
        <p className="text-sm text-muted-foreground">
          Không có phương pháp nào bắt buộc — chọn cách chia tiền hợp với bạn
          rồi chỉnh lại từng dòng.{" "}
          <Link href="/budget" className="underline underline-offset-3">
            Quay lại Ngân sách
          </Link>
        </p>
      </div>
      <Suspense
        fallback={<p className="text-sm text-muted-foreground">Đang tải…</p>}
      >
        <BudgetWizard />
      </Suspense>
    </div>
  );
}
