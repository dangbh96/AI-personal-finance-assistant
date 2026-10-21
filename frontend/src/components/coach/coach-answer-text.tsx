import Link from "next/link";
import { Fragment, type ReactNode } from "react";

// `**đậm**` hoặc `[nhãn](/đường-dẫn-nội-bộ)` — chỉ nhận link nội bộ bắt đầu bằng "/".
const INLINE = /\*\*([^*]+)\*\*|\[([^\]]+)\]\((\/[A-Za-z0-9/_\-?=&.%]*)\)/g;

function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) out.push(text.slice(last, index));
    if (match[1] !== undefined) {
      out.push(<strong key={index}>{match[1]}</strong>);
    } else {
      out.push(
        <Link key={index} href={match[3]} className="font-medium text-primary underline underline-offset-2">
          {match[2]}
        </Link>,
      );
    }
    last = index + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { kind: "heading"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

function parse(content: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of content.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const heading = /^(?:#+\s*)?\*\*([^*]+)\*\*:?$/.exec(line) ?? /^#+\s*(.+)$/.exec(line);
    const bullet = /^(?:[-•*]|\d+\.)\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", text: heading[1] });
    } else if (bullet) {
      const prev = blocks.at(-1);
      if (prev?.kind === "list") prev.items.push(bullet[1]);
      else blocks.push({ kind: "list", items: [bullet[1]] });
    } else {
      blocks.push({ kind: "paragraph", text: line });
    }
  }
  return blocks;
}

/** Hiển thị câu trả lời của Coach (markdown tối giản: tiêu đề in đậm, gạch đầu dòng, link). */
export function CoachAnswerText({ content }: { content: string }) {
  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed">
      {parse(content).map((block, i) => (
        <Fragment key={i}>
          {block.kind === "heading" && (
            <p className="pt-1 font-semibold text-foreground first:pt-0">{block.text}</p>
          )}
          {block.kind === "list" && (
            <ul className="ml-4 list-disc space-y-1">
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item)}</li>
              ))}
            </ul>
          )}
          {block.kind === "paragraph" && <p>{renderInline(block.text)}</p>}
        </Fragment>
      ))}
    </div>
  );
}
