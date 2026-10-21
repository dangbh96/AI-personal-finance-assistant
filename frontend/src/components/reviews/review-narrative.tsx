import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ReviewNarrative as Narrative } from "@/lib/api";

const FALLBACK_REASONS: Record<string, string> = {
  AI_NOT_CONFIGURED: "chưa cấu hình AI",
  AI_AUTH_FAILED: "khoá AI không hợp lệ",
  AI_RATE_LIMITED: "AI đang quá tải",
  AI_TIMEOUT: "AI phản hồi quá lâu",
  AI_UNAVAILABLE: "không kết nối được AI",
  AI_INVALID_OUTPUT: "AI trả kết quả không hợp lệ",
  validation_failed: "bản AI viết chưa qua kiểm tra số liệu / giọng văn",
};

/** Lý do dùng bản tóm tắt tự động, dạng câu ngắn cho UI. */
export function fallbackReasonLabel(reason: string | null | undefined): string {
  return (reason && FALLBACK_REASONS[reason]) ?? "AI tạm thời không dùng được";
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h3>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

/** What happened / Why / What to notice / Gợi ý — văn bản đã được backend kiểm tra. */
export function ReviewNarrative({
  narrative,
  model,
  title = "Nhìn lại tuần",
}: {
  narrative: Narrative;
  model: string | null;
  title?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {title}
          {narrative.fallback_used && (
            <Badge
              variant="secondary"
              title={`Dùng bản tự động vì ${fallbackReasonLabel(narrative.fallback_reason)}`}
            >
              Bản tóm tắt tự động
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          {narrative.fallback_used
            ? `Tóm tắt dựng từ số liệu (${fallbackReasonLabel(narrative.fallback_reason)}).`
            : `AI diễn giải số liệu đã tính sẵn${model ? ` · ${model}` : ""}.`}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Section title="Chuyện gì đã xảy ra?">{narrative.observation}</Section>
        <Section title="Vì sao?">{narrative.explanation}</Section>
        <Section title="Điều đáng chú ý">
          <ul className="list-disc space-y-1 pl-5">
            {narrative.notice.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </Section>
        {narrative.action && <Section title="Gợi ý">{narrative.action}</Section>}
      </CardContent>
    </Card>
  );
}
