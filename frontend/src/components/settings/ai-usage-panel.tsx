"use client";

import { useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, type AIUsageGroupBy, type AIUsageReport } from "@/lib/api";
import { formatDate, formatVND } from "@/lib/format";

const GROUP_LABELS: Record<AIUsageGroupBy, string> = {
  model: "Theo model",
  task: "Theo tác vụ",
  kind: "Theo loại lời gọi",
};

const COLUMN_LABELS: Record<AIUsageGroupBy, string> = {
  model: "Model",
  task: "Tác vụ",
  kind: "Loại lời gọi",
};

const NUMBER = new Intl.NumberFormat("vi-VN");

/** `/settings` → tab "Chi phí AI": token / chi phí ước tính / latency của các lời gọi OpenAI. */
export function AIUsagePanel() {
  const [groupBy, setGroupBy] = useState<AIUsageGroupBy>("model");
  const report = useApiData<AIUsageReport>(`/admin/ai-usage?group_by=${groupBy}`);
  const data = report.data;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <CardTitle>Chi phí AI</CardTitle>
          <CardDescription>
            {data
              ? `Từ ${formatDate(data.from_date)} đến ${formatDate(data.to_date)}. ${data.note}`
              : "Token và chi phí ước tính của các lời gọi OpenAI."}
          </CardDescription>
        </div>
        <Select
          items={GROUP_LABELS}
          value={groupBy}
          onValueChange={(value) => value && setGroupBy(value as AIUsageGroupBy)}
        >
          <SelectTrigger className="w-44" aria-label="Nhóm theo">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(GROUP_LABELS) as AIUsageGroupBy[]).map((key) => (
              <SelectItem key={key} value={key}>
                {GROUP_LABELS[key]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {report.error && (
          <p className="text-sm text-destructive">{describeError(report.error)}</p>
        )}
        {!data && !report.error && (
          <p className="text-sm text-muted-foreground">Đang tải…</p>
        )}
        {data && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Lời gọi" value={NUMBER.format(data.totals.calls)} />
              <Stat
                label="Token vào / ra"
                value={`${NUMBER.format(data.totals.input_tokens)} / ${NUMBER.format(data.totals.output_tokens)}`}
              />
              <Stat
                label="Chi phí ước tính"
                value={formatVND(data.totals.cost_estimate_vnd)}
              />
              <Stat label="Lỗi" value={NUMBER.format(data.totals.error_count)} />
            </div>
            {data.rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Chưa có lời gọi AI nào trong khoảng này.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{COLUMN_LABELS[data.group_by]}</TableHead>
                    <TableHead className="text-right">Lời gọi</TableHead>
                    <TableHead className="text-right">Token vào</TableHead>
                    <TableHead className="text-right">Token ra</TableHead>
                    <TableHead className="text-right">Chi phí</TableHead>
                    <TableHead className="text-right">Latency TB</TableHead>
                    <TableHead className="text-right">Lỗi</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.rows.map((row) => (
                    <TableRow key={row.key}>
                      <TableCell className="font-medium">{row.key}</TableCell>
                      <TableCell className="text-right">{NUMBER.format(row.calls)}</TableCell>
                      <TableCell className="text-right">
                        {NUMBER.format(row.input_tokens)}
                      </TableCell>
                      <TableCell className="text-right">
                        {NUMBER.format(row.output_tokens)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatVND(row.cost_estimate_vnd)}
                      </TableCell>
                      <TableCell className="text-right">
                        {NUMBER.format(row.latency_ms_avg)} ms
                      </TableCell>
                      <TableCell className="text-right">
                        {NUMBER.format(row.error_count)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-base font-semibold">{value}</p>
    </div>
  );
}
