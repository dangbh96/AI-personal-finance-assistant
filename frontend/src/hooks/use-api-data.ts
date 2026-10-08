"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, apiGet } from "@/lib/api";

type Result<T> = { key: string; data?: T; error?: ApiError };

/**
 * GET `path` (client-side) và tải lại khi `path` đổi hoặc khi gọi `reload()`.
 * Giữ `data` cũ trong lúc tải lại để bảng không bị nháy trắng.
 */
export function useApiData<T>(path: string) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const key = `${path}#${version}`;

  useEffect(() => {
    let active = true;
    apiGet<T>(path).then(
      (data) => {
        if (active) setResult({ key, data });
      },
      (err: unknown) => {
        if (!active) return;
        const error =
          err instanceof ApiError ? err : new ApiError(String(err), null);
        setResult((prev) => ({ key, data: prev?.data, error }));
      },
    );
    return () => {
      active = false;
    };
  }, [path, key]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  return {
    data: result?.data,
    error: result?.key === key ? result.error : undefined,
    loading: result?.key !== key,
    reload,
  };
}
