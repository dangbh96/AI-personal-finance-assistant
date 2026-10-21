"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  apiRequest,
  withQuery,
  type PyfProposal,
  type PyfProposalRequest,
} from "@/lib/api";

type State = { key: string; data?: PyfProposal; error?: ApiError };

/**
 * Gọi `POST /goals/pyf-proposal` (debounce) mỗi khi số user chỉnh đổi — phần còn thiếu, tổng
 * phân bổ, số còn lại để chi tiêu và cảnh báo đều do backend tính (không ghi DB).
 * `request = null` → không gọi (dùng đề xuất ban đầu).
 */
export function usePyfProposal(
  request: PyfProposalRequest | null,
  today: string | null,
  delayMs = 300,
) {
  const key = request ? JSON.stringify({ request, today }) : "";
  const [state, setState] = useState<State | null>(null);

  useEffect(() => {
    if (!key) return;
    let active = true;
    const timer = setTimeout(() => {
      const parsed = JSON.parse(key) as {
        request: PyfProposalRequest;
        today: string | null;
      };
      apiRequest<PyfProposal>(
        "POST",
        withQuery("/goals/pyf-proposal", { today: parsed.today }),
        parsed.request,
      ).then(
        (data) => {
          if (active) setState({ key, data });
        },
        (err: unknown) => {
          if (!active) return;
          const error =
            err instanceof ApiError ? err : new ApiError(String(err), null);
          setState((prev) => ({ key, data: prev?.data, error }));
        },
      );
    }, delayMs);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [key, delayMs]);

  const current = state?.key === key;
  return {
    data: key ? state?.data : undefined,
    error: current ? state?.error : undefined,
    loading: !!key && !current,
  };
}
