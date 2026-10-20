"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  apiRequest,
  type BudgetPreviewRequest,
  type BudgetPreviewResponse,
} from "@/lib/api";

type State = {
  key: string;
  data?: BudgetPreviewResponse;
  error?: ApiError;
};

/**
 * Gọi `POST /budgets/preview` (debounce) mỗi khi `request` đổi — mọi con số (phân bổ mặc định,
 * tổng, cảnh báo, so sánh 50/30/20) đều do backend tính. `request = null` → không gọi.
 */
export function useBudgetPreview(
  request: BudgetPreviewRequest | null,
  delayMs = 300,
) {
  const key = request ? JSON.stringify(request) : "";
  const [state, setState] = useState<State | null>(null);

  useEffect(() => {
    if (!key) return;
    let active = true;
    const timer = setTimeout(() => {
      apiRequest<BudgetPreviewResponse>("POST", "/budgets/preview", JSON.parse(key)).then(
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
    /** Kết quả gần nhất (có thể của request cũ trong lúc đang tính lại). */
    data: key ? state?.data : undefined,
    /** Kết quả đúng với `request` hiện tại. */
    fresh: current && !state?.error ? state?.data : undefined,
    error: current ? state?.error : undefined,
    loading: !!key && !current,
  };
}
