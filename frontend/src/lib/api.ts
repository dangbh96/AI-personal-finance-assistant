import type { components } from "@/lib/api-types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

// Type sinh từ OpenAPI của backend: `npm run gen:api` (backend phải đang chạy).
type Schemas = components["schemas"];
export type HealthResponse = Schemas["HealthResponse"];
export type Category = Schemas["CategoryRead"];
export type CategoryCreate = Schemas["CategoryCreate"];
export type CategoryUpdate = Schemas["CategoryUpdate"];
export type Transaction = Schemas["TransactionRead"];
export type TransactionCreate = Schemas["TransactionCreate"];
export type TransactionUpdate = Schemas["TransactionUpdate"];
export type TransactionList = Schemas["TransactionList"];
export type TransactionSummary = Schemas["TransactionSummary"];
export type Direction = Transaction["direction"];
export type SpendingType = NonNullable<Transaction["spending_type"]>;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Mã lỗi nghiệp vụ từ backend (`{"detail", "code"}`), nếu có. */
  get code(): string | null {
    const body = this.body as { code?: unknown } | null;
    return typeof body?.code === "string" ? body.code : null;
  }
}

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Tạo query string, bỏ qua giá trị rỗng/undefined. */
export function withQuery(
  path: string,
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  // Lỗi validate của FastAPI: danh sách {loc, msg}.
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : ""))
      .filter(Boolean)
      .join("; ");
  }
  return fallback;
}

/**
 * Gọi backend và parse JSON. Ném `ApiError` với `status = null` khi không kết nối được
 * (backend tắt / CORS / mạng), hoặc với HTTP status khi backend trả lỗi.
 */
export async function apiRequest<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      ...init,
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new ApiError(
      err instanceof Error ? err.message : "Network error",
      null,
    );
  }

  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(errorMessage(data, res.statusText), res.status, data);
  }
  return data as T;
}

export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return apiRequest<T>("GET", path, undefined, init);
}

/** Thông báo lỗi tiếng Việt thân thiện cho UI. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === null
      ? "Không kết nối được backend. Kiểm tra server đang chạy."
      : err.message;
  }
  return "Đã có lỗi xảy ra.";
}
