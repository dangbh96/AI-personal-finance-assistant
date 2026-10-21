import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { EvidenceItem } from "@/lib/api";
import { formatSignedVND, formatVND } from "@/lib/format";

/** Bảng "Dữ liệu đã dùng": các số liệu từ tool mà câu trả lời đã trích dẫn. */
export function EvidenceTable({ items }: { items: EvidenceItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="rounded-lg border">
      <p className="border-b px-3 py-2 text-xs font-medium text-muted-foreground">
        Dữ liệu đã dùng
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">Mã</TableHead>
            <TableHead>Danh mục / dòng</TableHead>
            <TableHead>Kỳ</TableHead>
            <TableHead>Chỉ số</TableHead>
            <TableHead className="text-right">Số tiền</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((e) => (
            <TableRow key={e.ref}>
              <TableCell className="font-mono text-xs text-muted-foreground">{e.ref}</TableCell>
              <TableCell className="font-medium">{e.label}</TableCell>
              <TableCell className="tabular-nums">{e.period}</TableCell>
              <TableCell className="text-muted-foreground">{e.metric}</TableCell>
              <TableCell className="text-right tabular-nums">
                {e.metric.startsWith("Chênh lệch") ? formatSignedVND(e.amount) : formatVND(e.amount)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
