"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiError, apiGet, type HealthResponse } from "@/lib/api";

type StatusState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "unreachable" };

type Tone = "ok" | "error" | "warn" | "pending";

const toneVariant = {
  ok: "default",
  error: "destructive",
  warn: "secondary",
  pending: "outline",
} as const;

async function fetchHealth(): Promise<StatusState> {
  try {
    return { kind: "ok", health: await apiGet<HealthResponse>("/health") };
  } catch (err) {
    // 503 vẫn có body HealthResponse: backend sống nhưng DB lỗi.
    if (err instanceof ApiError && err.status === 503 && err.body) {
      return { kind: "ok", health: err.body as HealthResponse };
    }
    return { kind: "unreachable" };
  }
}

function StatusRow({
  label,
  tone,
  text,
}: {
  label: string;
  tone: Tone;
  text: string;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={toneVariant[tone]}>{text}</Badge>
    </div>
  );
}

export function SystemStatusCard() {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    setState(await fetchHealth());
  }, []);

  useEffect(() => {
    let active = true;
    fetchHealth().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, []);

  const pending = { tone: "pending" as const, text: "Đang kiểm tra…" };
  let backend: { tone: Tone; text: string } = pending;
  let database: { tone: Tone; text: string } = pending;
  let ai: { tone: Tone; text: string } = pending;

  if (state.kind === "unreachable") {
    backend = { tone: "error", text: "Không kết nối được" };
    database = { tone: "pending", text: "Không rõ" };
    ai = { tone: "pending", text: "Không rõ" };
  } else if (state.kind === "ok") {
    const { health } = state;
    backend = { tone: "ok", text: "OK" };
    database =
      health.db === "ok"
        ? { tone: "ok", text: "OK" }
        : { tone: "error", text: "Lỗi" };
    ai = health.ai_configured
      ? { tone: "ok", text: "Đã cấu hình" }
      : { tone: "warn", text: "Chưa cấu hình" };
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Trạng thái hệ thống</CardTitle>
        <CardDescription>
          {state.kind === "ok"
            ? `Backend phiên bản ${state.health.version}`
            : "Kết nối Frontend → Backend → Database"}
        </CardDescription>
        <CardAction>
          <Button
            variant="outline"
            size="sm"
            onClick={refresh}
            disabled={state.kind === "loading"}
          >
            Kiểm tra lại
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="divide-y">
        <StatusRow label="Backend" {...backend} />
        <StatusRow label="Database" {...database} />
        <StatusRow label="AI (OpenAI)" {...ai} />
      </CardContent>
    </Card>
  );
}
