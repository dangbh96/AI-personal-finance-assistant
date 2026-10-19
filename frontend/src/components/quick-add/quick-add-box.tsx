"use client";

import { SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { TransactionDraftReview } from "@/components/quick-add/transaction-draft-review";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiData } from "@/hooks/use-api-data";
import {
  ApiError,
  apiRequest,
  describeError,
  type Category,
  type HealthResponse,
  type Preference,
  type TransactionParseRequest,
  type TransactionParseResponse,
} from "@/lib/api";
import { todayISO } from "@/lib/dates";
import { describePreference } from "@/lib/labels";

type ParseState = { id: number; result: TransactionParseResponse };

function browserTimeZone(): string | undefined {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

/** Nhập giao dịch bằng câu tự nhiên → AI tạo draft → user sửa/xác nhận rồi mới lưu. */
export function QuickAddBox() {
  const health = useApiData<HealthResponse>("/health");
  const categories = useApiData<Category[]>("/categories");
  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [parsed, setParsed] = useState<ParseState | null>(null);
  const [notice, setNotice] = useState<{
    saved: number;
    learned: Preference[];
  } | null>(null);

  const aiOff = notConfigured || health.data?.ai_configured === false;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = text.trim();
    if (!input || parsing) return;

    setParsing(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiRequest<TransactionParseResponse>(
        "POST",
        "/transactions/parse",
        {
          text: input,
          today: todayISO(),
          timezone: browserTimeZone(),
        } satisfies TransactionParseRequest,
      );
      setParsed((prev) => ({ id: (prev?.id ?? 0) + 1, result }));
    } catch (err) {
      if (err instanceof ApiError && err.code === "AI_NOT_CONFIGURED") {
        setNotConfigured(true);
      } else {
        setError(describeError(err));
      }
    } finally {
      setParsing(false);
    }
  }

  const handleDone = useCallback(
    (savedCount: number, learned: Preference[]) => {
      setParsed(null);
      if (savedCount > 0) setText("");
      setNotice({ saved: savedCount, learned });
    },
    [],
  );

  return (
    <Card className="w-full max-w-3xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SparklesIcon className="size-4 text-violet-500" aria-hidden />
          Nhập nhanh bằng câu tự nhiên
        </CardTitle>
        <CardDescription>
          Ví dụ: “Hôm nay ăn phở 55k” hoặc “sáng cafe 35k, trưa cơm 60k”. AI
          chỉ tạo bản nháp — bạn kiểm tra rồi mới lưu.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            aria-label="Câu nhập giao dịch"
            placeholder="Hôm nay ăn phở 55k"
            maxLength={500}
            autoComplete="off"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={parsing}
          />
          <Button type="submit" disabled={parsing || aiOff || !text.trim()}>
            {parsing ? "Đang phân tích…" : "Phân tích"}
          </Button>
        </form>

        {aiOff && (
          <p role="status" className="text-sm text-muted-foreground">
            Chưa cấu hình AI. Bạn vẫn có thể nhập thủ công ở{" "}
            <Link
              href="/transactions"
              className="text-foreground underline underline-offset-3"
            >
              Giao dịch
            </Link>
            .
          </p>
        )}

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {notice && (
          <div role="status" className="flex flex-col gap-1 text-sm">
            <p>
              {notice.saved > 0 ? (
                <>
                  Đã lưu {notice.saved} giao dịch.{" "}
                  <Link
                    href="/transactions"
                    className="text-muted-foreground underline underline-offset-3"
                  >
                    Xem trong Giao dịch
                  </Link>
                </>
              ) : (
                "Không có giao dịch nào được lưu."
              )}
            </p>
            {notice.learned.map((preference) => (
              <p
                key={preference.id}
                className="flex items-center gap-1.5 text-violet-700 dark:text-violet-300"
              >
                <SparklesIcon className="size-3.5 shrink-0" aria-hidden />
                <span>
                  Đã học cách phân loại này: {describePreference(preference)}.{" "}
                  <Link
                    href="/settings?tab=preferences"
                    className="text-muted-foreground underline underline-offset-3"
                  >
                    Xem / xoá
                  </Link>
                </span>
              </p>
            ))}
          </div>
        )}

        {parsed && (
          <TransactionDraftReview
            key={parsed.id}
            result={parsed.result}
            categories={categories.data ?? []}
            onDone={handleDone}
          />
        )}
      </CardContent>
    </Card>
  );
}
