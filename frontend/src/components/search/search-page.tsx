"use client";

import { SearchIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { io } from "next/cache";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  withQuery,
  type ReindexResult,
  type SearchMatchReason,
  type TransactionSearchResponse,
  type TransactionSearchResult,
} from "@/lib/api";
import { currentMonth, monthToRange, shiftMonth } from "@/lib/dates";
import { formatDate, formatSignedVND, formatVND } from "@/lib/format";
import { SOURCE_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

const LIMITS = ["10", "20", "50"] as const;
const EXAMPLES = ["ăn ngoài", "đi lại", "cà phê", "khoản lớn mua sắm"];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const MATCH_LABELS: Record<SearchMatchReason, string> = {
  semantic: "Theo ý nghĩa",
  keyword: "Theo từ khoá",
  hybrid: "Ý nghĩa + từ khoá",
};

type Params = { q: string; from: string; to: string; limit: string };

function readParams(params: URLSearchParams): Params {
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const limit = params.get("limit") ?? "20";
  return {
    q: (params.get("q") ?? "").trim(),
    from: ISO_DATE.test(from) ? from : "",
    to: ISO_DATE.test(to) ? to : "",
    limit: (LIMITS as readonly string[]).includes(limit) ? limit : "20",
  };
}

/**
 * `/search` (Phase 15): tìm giao dịch theo ý nghĩa tiếng Việt (embedding + từ khoá). Trạng thái
 * nằm trên URL (`?q=&from=&to=&limit=`) để tải lại / chia sẻ được.
 */
export function SearchPage() {
  // Nút "Tháng này / Tháng trước" phụ thuộc thời điểm hiện tại.
  use(io());
  const router = useRouter();
  const pathname = usePathname();
  const params = readParams(useSearchParams());
  const [text, setText] = useState(params.q);
  const [selected, setSelected] = useState<TransactionSearchResult | null>(null);

  function navigate(patch: Partial<Params>) {
    const next = { ...params, ...patch };
    router.replace(
      withQuery(pathname, {
        q: next.q,
        from: next.from,
        to: next.to,
        limit: next.limit === "20" ? "" : next.limit,
      }),
    );
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate({ q: text.trim() });
  }

  const thisMonth = currentMonth();
  const ranges = [
    { label: "Tháng này", ...monthToRange(thisMonth) },
    { label: "Tháng trước", ...monthToRange(shiftMonth(thisMonth, -1)) },
    { label: "Mọi lúc", from: "", to: "" },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Tìm kiếm giao dịch</h1>
        <p className="text-sm text-muted-foreground">
          Tìm theo ý nghĩa: “ăn ngoài” sẽ thấy cả “nhà hàng”, “bún chả”; “đi lại” thấy “grab”,
          “xăng” — không cần gõ đúng từ trong ghi chú.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-64 flex-1 flex-col gap-1.5">
            <Label htmlFor="search-q">Nội dung cần tìm</Label>
            <Input
              id="search-q"
              value={text}
              maxLength={200}
              placeholder="vd: ăn ngoài, đi lại, Highlands"
              onChange={(e) => setText(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="search-from">Từ ngày</Label>
            <Input
              id="search-from"
              type="date"
              value={params.from}
              max={params.to || undefined}
              onChange={(e) => navigate({ from: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="search-to">Đến ngày</Label>
            <Input
              id="search-to"
              type="date"
              value={params.to}
              min={params.from || undefined}
              onChange={(e) => navigate({ to: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Số kết quả</Label>
            <Select
              items={Object.fromEntries(LIMITS.map((l) => [l, `${l} kết quả`]))}
              value={params.limit}
              onValueChange={(v) => v && navigate({ limit: String(v) })}
            >
              <SelectTrigger aria-label="Số kết quả" className="min-w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LIMITS.map((l) => (
                  <SelectItem key={l} value={l}>
                    {l} kết quả
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={!text.trim()}>
            <SearchIcon data-icon="inline-start" />
            Tìm
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Khoảng thời gian:</span>
          {ranges.map((r) => {
            const active = params.from === r.from && params.to === r.to;
            return (
              <Button
                key={r.label}
                type="button"
                size="sm"
                variant={active ? "secondary" : "ghost"}
                aria-pressed={active}
                onClick={() => navigate({ from: r.from, to: r.to })}
              >
                {r.label}
              </Button>
            );
          })}
        </div>
      </form>

      {params.q ? (
        <SearchResults params={params} onSelect={setSelected} />
      ) : (
        <EmptyState
          onPick={(q) => {
            setText(q);
            navigate({ q });
          }}
        />
      )}

      <ResultDialog result={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-start gap-3 py-6">
        <SparklesIcon className="size-5 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Gõ một nhu cầu chi tiêu bằng lời của bạn. Thử một ví dụ:
        </p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <Button key={q} type="button" variant="outline" size="sm" onClick={() => onPick(q)}>
              {q}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SearchResults({
  params,
  onSelect,
}: {
  params: Params;
  onSelect: (r: TransactionSearchResult) => void;
}) {
  const path = withQuery("/search/transactions", {
    q: params.q,
    from: params.from,
    to: params.to,
    limit: params.limit,
  });
  const { data, error, loading, reload } = useApiData<TransactionSearchResponse>(path);
  const [indexing, setIndexing] = useState(false);
  const [indexMessage, setIndexMessage] = useState<string | null>(null);

  async function reindex() {
    setIndexing(true);
    setIndexMessage(null);
    try {
      const res = await apiRequest<ReindexResult>("POST", "/search/transactions/reindex", {});
      setIndexMessage(
        `Đã lập chỉ mục ${res.processed_count} giao dịch` +
          (res.remaining_count ? `, còn ${res.remaining_count}.` : "."),
      );
      reload();
    } catch (err) {
      setIndexMessage(describeError(err));
    } finally {
      setIndexing(false);
    }
  }

  if (error && !data) {
    const aiDown = error.status === 503 || error.status === 502;
    return (
      <p role="alert" className="text-sm text-destructive">
        {aiDown
          ? `Tìm kiếm theo ý nghĩa cần AI nhưng hiện chưa dùng được: ${error.message} Bạn vẫn có thể lọc theo ghi chú ở trang `
          : describeError(error)}
        {aiDown && (
          <Link href="/transactions" className="underline">
            Giao dịch
          </Link>
        )}
      </p>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Đang tìm…</p>;
  }

  return (
    <div className={cn("flex flex-col gap-4", loading && "opacity-60")}>
      <div className="grid gap-3 sm:grid-cols-4">
        <SummaryCard title="Kết quả" value={String(data.result_count)} />
        <SummaryCard title="Tổng chi" value={formatVND(data.expense_total)} />
        <SummaryCard title="Tổng thu" value={formatVND(data.income_total)} />
        <SummaryCard title="Thu − chi" value={formatSignedVND(data.net)} />
      </div>

      {data.missing_embedding_count > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed p-3 text-sm">
          <span className="text-muted-foreground">
            {data.missing_embedding_count} giao dịch trong khoảng này chưa được lập chỉ mục ngữ
            nghĩa nên chỉ tìm được theo từ khoá.
          </span>
          <Button size="sm" variant="outline" onClick={reindex} disabled={indexing}>
            {indexing ? "Đang lập chỉ mục…" : "Lập chỉ mục ngay"}
          </Button>
          {indexMessage && <span>{indexMessage}</span>}
        </div>
      )}

      {data.results.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Không tìm thấy giao dịch phù hợp với “{data.query}”
          {params.from || params.to ? " trong khoảng thời gian này" : ""}. Bạn thử diễn đạt
          khác hoặc mở rộng khoảng thời gian nhé.
        </p>
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border">
          {data.results.map((r) => (
            <li key={r.transaction_id}>
              <button
                type="button"
                onClick={() => onSelect(r)}
                className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-muted"
              >
                <span className="w-24 shrink-0 text-sm text-muted-foreground">
                  {formatDate(r.occurred_on)}
                </span>
                <span className="min-w-40 flex-1">
                  <span className="block font-medium">{r.note || "(không ghi chú)"}</span>
                  <span className="text-xs text-muted-foreground">
                    {MATCH_LABELS[r.match_reason]} · điểm {r.score.toFixed(2)}
                  </span>
                </span>
                <Badge variant="secondary">
                  {r.category_icon ? `${r.category_icon} ` : ""}
                  {r.category_name}
                </Badge>
                <span
                  className={cn(
                    "w-32 text-right font-medium tabular-nums",
                    r.direction === "income" && "text-emerald-600",
                  )}
                >
                  {r.direction === "income" ? "+" : "−"}
                  {formatVND(r.amount)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-sm font-normal text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-lg font-semibold tabular-nums">{value}</CardContent>
    </Card>
  );
}

function ResultDialog({
  result,
  onOpenChange,
}: {
  result: TransactionSearchResult | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={result !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {result && (
          <>
            <DialogHeader>
              <DialogTitle>{result.note || "(không ghi chú)"}</DialogTitle>
              <DialogDescription>
                {formatDate(result.occurred_on)} · {SOURCE_LABELS[result.source]}
              </DialogDescription>
            </DialogHeader>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Số tiền</dt>
              <dd className="font-medium">
                {result.direction === "income" ? "+" : "−"}
                {formatVND(result.amount)}
              </dd>
              <dt className="text-muted-foreground">Danh mục</dt>
              <dd>
                {result.category_icon} {result.category_name}
              </dd>
              {result.spending_type && (
                <>
                  <dt className="text-muted-foreground">Loại chi tiêu</dt>
                  <dd>{SPENDING_TYPE_LABELS[result.spending_type]}</dd>
                </>
              )}
              <dt className="text-muted-foreground">Vì sao khớp</dt>
              <dd>
                {MATCH_LABELS[result.match_reason]}
                {result.semantic_score !== null &&
                  ` · tương đồng ${result.semantic_score.toFixed(2)}`}
                {result.keyword_boost > 0 && ` · từ khoá ${result.keyword_boost}`}
              </dd>
            </dl>
            <DialogFooter>
              <Link
                href={withQuery("/transactions", {
                  month: result.occurred_on.slice(0, 7),
                  q: result.note ?? "",
                })}
                className={buttonVariants({ variant: "outline" })}
              >
                Mở trong Giao dịch
              </Link>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
