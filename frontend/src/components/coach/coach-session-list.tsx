"use client";

import { CheckIcon, PencilIcon, PlusIcon, Trash2Icon, XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  apiRequest,
  describeError,
  type ChatSession,
  type ChatSessionSummary,
  type ChatSessionUpdate,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

function SessionItem({
  session,
  active,
  onSelect,
  onChanged,
  onDeleted,
}: {
  session: ChatSessionSummary;
  active: boolean;
  onSelect: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [mode, setMode] = useState<"view" | "rename" | "delete">("view");
  const [title, setTitle] = useState(session.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function rename() {
    const next = title.trim();
    if (!next || next === session.title) {
      setMode("view");
      return;
    }
    setBusy(true);
    try {
      const body: ChatSessionUpdate = { title: next };
      await apiRequest<ChatSession>("PATCH", `/coach/sessions/${session.id}`, body);
      setMode("view");
      setError(null);
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await apiRequest("DELETE", `/coach/sessions/${session.id}`);
      onDeleted();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  }

  if (mode === "rename") {
    return (
      <li className="flex flex-col gap-1 rounded-lg bg-muted p-2">
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            void rename();
          }}
        >
          <Input
            autoFocus
            value={title}
            maxLength={120}
            aria-label="Tên cuộc trò chuyện"
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button type="submit" size="icon" variant="ghost" disabled={busy} aria-label="Lưu tên">
            <CheckIcon />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label="Huỷ đổi tên"
            onClick={() => {
              setTitle(session.title);
              setMode("view");
            }}
          >
            <XIcon />
          </Button>
        </form>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </li>
    );
  }

  return (
    <li
      className={cn(
        "group flex flex-col gap-1 rounded-lg p-2 hover:bg-muted",
        active && "bg-muted",
      )}
    >
      <div className="flex items-start gap-1">
        <button
          type="button"
          onClick={onSelect}
          aria-current={active ? "true" : undefined}
          className="flex min-w-0 flex-1 flex-col items-start text-left"
        >
          <span className="w-full truncate text-sm font-medium">{session.title}</span>
          <span className="w-full truncate text-xs text-muted-foreground">
            {session.last_message_preview ?? "Chưa có tin nhắn"}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatDate(session.updated_at.slice(0, 10))} · {session.message_count} tin nhắn
          </span>
        </button>
        {mode === "view" && (
          <div className="flex shrink-0 opacity-60 group-hover:opacity-100">
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="Đổi tên"
              onClick={() => setMode("rename")}
            >
              <PencilIcon />
            </Button>
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="Xoá cuộc trò chuyện"
              onClick={() => setMode("delete")}
            >
              <Trash2Icon />
            </Button>
          </div>
        )}
      </div>
      {mode === "delete" && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Xoá cuộc trò chuyện này?</span>
          <Button size="xs" variant="destructive" disabled={busy} onClick={() => void remove()}>
            Xoá
          </Button>
          <Button size="xs" variant="ghost" onClick={() => setMode("view")}>
            Huỷ
          </Button>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </li>
  );
}

export function CoachSessionList({
  sessions,
  loading,
  error,
  activeId,
  onSelect,
  onNew,
  onChanged,
  onDeleted,
}: {
  sessions: ChatSessionSummary[];
  loading: boolean;
  error: string | null;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onChanged: () => void;
  onDeleted: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <Button onClick={onNew} variant="outline">
        <PlusIcon />
        Cuộc trò chuyện mới
      </Button>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && sessions.length === 0 && (
        <p className="text-sm text-muted-foreground">Đang tải…</p>
      )}
      {!loading && !error && sessions.length === 0 && (
        <p className="text-sm text-muted-foreground">Chưa có cuộc trò chuyện nào.</p>
      )}
      <ul className="flex flex-col gap-1">
        {sessions.map((s) => (
          <SessionItem
            key={s.id}
            session={s}
            active={s.id === activeId}
            onSelect={() => onSelect(s.id)}
            onChanged={onChanged}
            onDeleted={() => onDeleted(s.id)}
          />
        ))}
      </ul>
    </div>
  );
}
