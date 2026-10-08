const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * GET JSON từ backend. Ném `ApiError` với `status = null` khi không kết nối được
 * (backend tắt / CORS / mạng), hoặc với HTTP status khi backend trả lỗi.
 */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      method: "GET",
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (err) {
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      null,
    );
  }

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(detail, res.status, body);
  }
  return body as T;
}

export type HealthResponse = {
  status: "ok" | "degraded";
  db: "ok" | "error";
  ai_configured: boolean;
  version: string;
};
