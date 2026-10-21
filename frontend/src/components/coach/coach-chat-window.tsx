"use client";

import { Loader2Icon, RotateCcwIcon, SendIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { CoachMessageBubble } from "@/components/coach/coach-message-bubble";
import { SuggestedQuestionChips } from "@/components/coach/suggested-question-chips";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  apiGet,
  apiRequest,
  describeError,
  type ChatMessage,
  type ChatSession,
  type ChatSessionCreate,
  type ChatSessionDetail,
  type CoachMessageCreate,
  type CoachMessageResponse,
} from "@/lib/api";
import { MAX_MESSAGE_LENGTH, coachErrorHint } from "@/lib/coach";

type SendError = { text: string; hint: string; question: string; saved: boolean };

function pendingMessage(content: string, sessionId: string | null): ChatMessage {
  return {
    id: `pending-${crypto.randomUUID()}`,
    session_id: sessionId ?? "",
    role: "user",
    content,
    tool_calls: null,
    evidence: null,
    metadata: null,
    created_at: new Date().toISOString(),
  };
}

/**
 * Khung chat của một session (`initialSessionId = null` → cuộc trò chuyện mới: session chỉ được
 * tạo khi gửi câu hỏi đầu tiên). Plain JSON — chờ backend chạy xong `coach_graph`.
 */
export function CoachChatWindow({
  initialSessionId,
  today,
  onSessionCreated,
  onActivity,
}: {
  initialSessionId: string | null;
  today: string;
  onSessionCreated: (id: string) => void;
  onActivity: () => void;
}) {
  const [loadId] = useState(initialSessionId);
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(initialSessionId !== null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<SendError | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loadId === null) return;
    let active = true;
    apiGet<ChatSessionDetail>(`/coach/sessions/${loadId}`).then(
      (detail) => {
        if (!active) return;
        setMessages(detail.messages);
        setLoading(false);
      },
      (err: unknown) => {
        if (!active) return;
        setLoadError(describeError(err));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [loadId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, sending]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || sending) return;
    setSending(true);
    setSendError(null);
    setDraft("");
    const pending = pendingMessage(content, sessionId);
    setMessages((prev) => [...prev, pending]);
    try {
      let id = sessionId;
      if (id === null) {
        const body: ChatSessionCreate = {};
        const created = await apiRequest<ChatSession>("POST", "/coach/sessions", body);
        id = created.id;
        setSessionId(id);
        onSessionCreated(id);
      }
      const body: CoachMessageCreate = { content, today };
      const res = await apiRequest<CoachMessageResponse>(
        "POST",
        `/coach/sessions/${id}/messages`,
        body,
      );
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== pending.id),
        res.user_message,
        res.assistant_message,
      ]);
    } catch (err) {
      const apiError = err instanceof ApiError ? err : null;
      // Backend lưu câu hỏi trước khi gọi AI → lỗi AI (5xx) vẫn giữ câu hỏi trong lịch sử.
      const saved = apiError?.status != null && apiError.status >= 500;
      if (!saved) setMessages((prev) => prev.filter((m) => m.id !== pending.id));
      setSendError({
        text: describeError(err),
        hint: coachErrorHint(apiError?.code ?? null),
        question: content,
        saved,
      });
    } finally {
      setSending(false);
      onActivity();
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Đang tải cuộc trò chuyện…</p>;
  }
  if (loadError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {loadError}
      </p>
    );
  }

  return (
    <div className="flex min-h-[60vh] flex-col gap-4">
      <div className="flex flex-1 flex-col gap-4">
        {messages.length === 0 && !sending && (
          <div className="flex flex-col gap-3 rounded-xl border border-dashed p-6">
            <p className="font-medium">Hỏi Coach về chi tiêu và ngân sách của bạn</p>
            <p className="text-sm text-muted-foreground">
              Coach đọc số liệu thật (giao dịch, ngân sách, tư vấn, review) qua các công cụ chỉ đọc,
              trả lời theo Quan sát → Vì sao → Gợi ý và kèm bảng dữ liệu đã dùng. Coach không tự
              sửa giao dịch hay ngân sách.
            </p>
            <SuggestedQuestionChips onPick={(q) => void send(q)} disabled={sending} />
          </div>
        )}
        {messages.map((m) => (
          <CoachMessageBubble key={m.id} message={m} />
        ))}
        {sending && (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Coach đang đọc dữ liệu...
          </p>
        )}
        {sendError && (
          <div
            role="alert"
            className="flex flex-col gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm"
          >
            <p className="font-medium text-destructive">Coach chưa trả lời được</p>
            <p>{sendError.text}</p>
            {sendError.hint && <p className="text-muted-foreground">{sendError.hint}</p>}
            {sendError.saved && (
              <p className="text-xs text-muted-foreground">
                Câu hỏi của bạn vẫn được lưu trong cuộc trò chuyện.
              </p>
            )}
            <div>
              <Button size="sm" variant="outline" onClick={() => void send(sendError.question)}>
                <RotateCcwIcon />
                Gửi lại
              </Button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {messages.length > 0 && (
        <SuggestedQuestionChips onPick={(q) => void send(q)} disabled={sending} />
      )}
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <textarea
          value={draft}
          rows={2}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder="Ví dụ: Tao nên giảm khoản nào?"
          aria-label="Câu hỏi cho Coach"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send(draft);
            }
          }}
          className="min-h-16 w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <Button type="submit" disabled={sending || !draft.trim()}>
          <SendIcon />
          Gửi
        </Button>
      </form>
    </div>
  );
}
