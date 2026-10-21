"use client";

import { io } from "next/cache";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { use, useState } from "react";

import { CoachChatWindow } from "@/components/coach/coach-chat-window";
import { CoachSessionList } from "@/components/coach/coach-session-list";
import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { useApiData } from "@/hooks/use-api-data";
import { describeError, type ChatSessionList } from "@/lib/api";

/**
 * `/coach?session=<id>`: Financial Coach full page — danh sách cuộc trò chuyện + khung chat.
 * `?today=YYYY-MM-DD` (tuỳ chọn) đặt "hôm nay" cho Coach như các trang review.
 */
export function CoachPage() {
  use(io());
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const today = useReviewToday();
  const selected = params.get("session");
  const sessions = useApiData<ChatSessionList>("/coach/sessions?limit=50");

  // Session vừa tạo khi gửi câu hỏi đầu tiên giữ nguyên khung chat (không tải lại).
  const [created, setCreated] = useState<string | null>(null);
  const [draftKey, setDraftKey] = useState(0);
  const chatKey = selected && selected !== created ? selected : `draft-${draftKey}`;

  function navigate(sessionId: string | null) {
    const next = new URLSearchParams(params.toString());
    if (sessionId) next.set("session", sessionId);
    else next.delete("session");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  function startNew() {
    setCreated(null);
    setDraftKey((k) => k + 1);
    navigate(null);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Financial Coach</h1>
        <p className="text-sm text-muted-foreground">
          Hỏi bằng tiếng Việt về chi tiêu, ngân sách, review — Coach trả lời dựa trên dữ liệu thật,
          kèm bằng chứng, và để bạn tự quyết định.
        </p>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="min-w-0">
          <CoachSessionList
            sessions={sessions.data?.items ?? []}
            loading={sessions.loading}
            error={sessions.error ? describeError(sessions.error) : null}
            activeId={selected}
            onSelect={(id) => {
              if (id !== selected) navigate(id);
            }}
            onNew={startNew}
            onChanged={sessions.reload}
            onDeleted={(id) => {
              sessions.reload();
              if (id === selected) startNew();
            }}
          />
        </aside>
        <section className="min-w-0">
          <CoachChatWindow
            key={chatKey}
            initialSessionId={selected}
            today={today}
            onSessionCreated={(id) => {
              setCreated(id);
              navigate(id);
            }}
            onActivity={sessions.reload}
          />
        </section>
      </div>
    </div>
  );
}
