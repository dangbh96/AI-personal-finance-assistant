"use client";

import { BookOpenIcon } from "lucide-react";
import { useState } from "react";

import { CoachAnswerText } from "@/components/coach/coach-answer-text";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, type CitationItem, type KnowledgeChunk } from "@/lib/api";

/**
 * Khối "Nguồn" của câu trả lời Coach (Phase 16): danh sách trích dẫn thu gọn được; bấm một nguồn
 * → drawer (dialog) hiện tiêu đề, mục, đường dẫn tài liệu và đoạn trích (tải toàn văn đoạn).
 */
export function CitationList({ items }: { items: CitationItem[] }) {
  const [open, setOpen] = useState<CitationItem | null>(null);
  if (items.length === 0) return null;
  return (
    <>
      <details open className="rounded-lg border bg-muted/30 text-sm">
        <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 font-medium">
          <BookOpenIcon className="size-4" />
          Nguồn ({items.length})
        </summary>
        <ul className="flex flex-col gap-1 px-3 pb-3">
          {items.map((c) => (
            <li key={c.ref}>
              <button
                type="button"
                onClick={() => setOpen(c)}
                className="w-full rounded-md px-2 py-1 text-left hover:bg-muted"
              >
                <span className="mr-2 font-mono text-xs text-muted-foreground">{c.ref}</span>
                <span className="font-medium">{c.title}</span>
                {c.heading && <span className="text-muted-foreground"> — {c.heading}</span>}
                <span className="block pl-7 text-xs text-muted-foreground">{c.source}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>
      <CitationDrawer citation={open} onOpenChange={(v) => !v && setOpen(null)} />
    </>
  );
}

function CitationDrawer({
  citation,
  onOpenChange,
}: {
  citation: CitationItem | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={citation !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        {citation && (
          <>
            <DialogHeader>
              <DialogTitle>{citation.title}</DialogTitle>
              <DialogDescription>
                {citation.heading ? `${citation.heading} · ` : ""}
                <span className="font-mono">{citation.source}</span>
              </DialogDescription>
            </DialogHeader>
            <ChunkContent citation={citation} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ChunkContent({ citation }: { citation: CitationItem }) {
  const { data, error } = useApiData<KnowledgeChunk>(`/knowledge/chunks/${citation.chunk_id}`);
  return (
    <div className="flex flex-col gap-2 text-sm">
      <CoachAnswerText content={data?.content ?? citation.snippet} />
      {error && (
        <p className="text-xs text-muted-foreground">
          Chỉ hiện đoạn trích đã lưu ({describeError(error)}).
        </p>
      )}
      {data && data.headings.length > 1 && (
        <p className="text-xs text-muted-foreground">Gồm các mục: {data.headings.join(" · ")}</p>
      )}
    </div>
  );
}
