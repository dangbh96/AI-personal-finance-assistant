import { AdviceCard } from "@/components/budget-advice/advice-card";
import type { BudgetAdvice } from "@/lib/api";
import type { AdviceStatusFilter } from "@/lib/advice";

const EMPTY_TEXT: Record<AdviceStatusFilter, string> = {
  open: "Không còn tư vấn nào chờ bạn quyết định.",
  accepted: "Chưa áp dụng tư vấn nào trong tháng này.",
  dismissed: "Chưa bỏ qua tư vấn nào trong tháng này.",
  all: "Chưa có tư vấn cho tháng này.",
};

/** Danh sách thẻ tư vấn đã lọc theo trạng thái (thứ tự dòng ngân sách). */
export function BudgetAdviceList({
  items,
  filter,
  onChanged,
}: {
  items: BudgetAdvice[];
  filter: AdviceStatusFilter;
  onChanged: (message: string | null) => void;
}) {
  const visible = filter === "all" ? items : items.filter((a) => a.status === filter);
  if (visible.length === 0) {
    return <p className="text-sm text-muted-foreground">{EMPTY_TEXT[filter]}</p>;
  }
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      {visible.map((advice) => (
        <AdviceCard key={advice.id} advice={advice} onChanged={onChanged} />
      ))}
    </div>
  );
}
