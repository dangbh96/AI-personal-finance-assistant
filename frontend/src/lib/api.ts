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
export type TransactionCreateResult = Schemas["TransactionCreateResult"];
export type TransactionUpdate = Schemas["TransactionUpdate"];
export type TransactionList = Schemas["TransactionList"];
export type TransactionSummary = Schemas["TransactionSummary"];
export type TransactionDraft = Schemas["TransactionDraft"];
export type TransactionParseRequest = Schemas["TransactionParseRequest"];
export type TransactionParseResponse = Schemas["TransactionParseResponse"];
export type Preference = Schemas["PreferenceRead"];
export type PreferenceList = Schemas["PreferenceList"];
export type PreferenceCreate = Schemas["PreferenceCreate"];
export type PreferenceDraft = Schemas["PreferenceDraft"];
export type PreferenceParseRequest = Schemas["PreferenceParseRequest"];
export type Budget = Schemas["BudgetRead"];
export type BudgetList = Schemas["BudgetList"];
export type BudgetCreate = Schemas["BudgetCreate"];
export type BudgetUpdate = Schemas["BudgetUpdate"];
export type BudgetCopyRequest = Schemas["BudgetCopyRequest"];
export type BudgetPreviewRequest = Schemas["BudgetPreviewRequest"];
export type BudgetPreviewResponse = Schemas["BudgetPreviewResponse"];
export type BudgetAllocationInput = Schemas["BudgetAllocationInput"];
export type BudgetAllocationDraft = Schemas["BudgetAllocationDraft"];
export type BudgetTotals = Schemas["BudgetTotals"];
export type BudgetWarning = Schemas["BudgetWarning"];
export type FiftyThirtyTwentyReference = Schemas["FiftyThirtyTwentyReference"];
export type BudgetJar = Schemas["BudgetJarRead"];
export type BudgetJarList = Schemas["BudgetJarList"];
export type BudgetStatusReport = Schemas["BudgetStatusRead"];
export type BudgetStatusTotals = Schemas["BudgetStatusTotals"];
export type AllocationStatus = Schemas["AllocationStatusRead"];
export type TopContributor = Schemas["TopContributorRead"];
export type MonthProgress = Schemas["MonthProgressRead"];
export type MonthSummary = Schemas["MonthSummaryRead"];
export type WeeklyReview = Schemas["WeeklyReviewRead"];
export type WeeklyReviewList = Schemas["WeeklyReviewList"];
export type WeeklyReviewGenerateRequest = Schemas["WeeklyReviewGenerateRequest"];
export type ReviewMetrics = Schemas["ReviewMetrics"];
export type ReviewNarrative = Schemas["ReviewNarrative"];
export type ReviewHighlights = Schemas["ReviewHighlights"];
export type CategoryChange = Schemas["CategoryChange"];
export type RepeatedCluster = Schemas["RepeatedCluster"];
export type ReviewTransaction = Schemas["ReviewTransaction"];
export type ReflectionAnswer = Schemas["ReflectionAnswerRead"];
export type ReflectionCreate = Schemas["ReflectionCreate"];
export type PendingWeeklyReview = Schemas["PendingWeeklyReviewRead"];
export type MonthlyReview = Schemas["MonthlyReviewRead"];
export type MonthlyReviewList = Schemas["MonthlyReviewList"];
export type MonthlyReviewGenerateRequest = Schemas["MonthlyReviewGenerateRequest"];
export type MonthlyReviewMetrics = Schemas["MonthlyReviewMetrics"];
export type MonthlyBudgetSummary = Schemas["MonthlyBudgetSummary"];
export type BudgetLineSummary = Schemas["BudgetLineSummary"];
export type WeeklyReflectionDigest = Schemas["WeeklyReflectionDigest"];
export type BudgetAdvice = Schemas["BudgetAdviceRead"];
export type BudgetAdviceList = Schemas["BudgetAdviceList"];
export type BudgetAdviceEvidence = Schemas["BudgetAdviceEvidence"];
export type AdviceTransaction = Schemas["AdviceTransaction"];
export type AdviceHistoryMonth = Schemas["AdviceHistoryMonth"];
export type AdviceNarrative = Schemas["AdviceNarrative"];
export type BudgetAdviceGenerateRequest = Schemas["BudgetAdviceGenerateRequest"];
export type BudgetAdviceAcceptRequest = Schemas["BudgetAdviceAcceptRequest"];
export type BudgetAdviceAcceptResult = Schemas["BudgetAdviceAcceptResult"];
export type BudgetAdviceDismissRequest = Schemas["BudgetAdviceDismissRequest"];
export type AdvisorSettings = Schemas["AdvisorSettings"];
export type AdvisorSettingsUpdate = Schemas["AdvisorSettingsUpdate"];
export type BudgetZoneList = Schemas["BudgetZoneList"];
export type BudgetZone = Schemas["BudgetZoneRead"];
export type AllocationZone = Schemas["AllocationZoneRead"];
export type AutoZoneDetail = Schemas["AutoZoneDetailRead"];
export type ZoneUpdate = Schemas["ZoneUpdate"];
export type ZoneRecalculateRequest = Schemas["ZoneRecalculateRequest"];
export type BudgetAllocation = Schemas["BudgetAllocationRead"];
export type ChatSession = Schemas["ChatSessionRead"];
export type ChatSessionSummary = Schemas["ChatSessionSummary"];
export type ChatSessionList = Schemas["ChatSessionList"];
export type ChatSessionDetail = Schemas["ChatSessionDetail"];
export type ChatSessionCreate = Schemas["ChatSessionCreate"];
export type ChatSessionUpdate = Schemas["ChatSessionUpdate"];
export type ChatMessage = Schemas["ChatMessageRead"];
export type ChatMessageMetadata = Schemas["ChatMessageMetadata"];
export type ToolTraceItem = Schemas["ToolTraceItem"];
export type EvidenceItem = Schemas["EvidenceItem"];
export type CoachMessageCreate = Schemas["CoachMessageCreate"];
export type CoachMessageResponse = Schemas["CoachMessageResponse"];
export type CoachGuardStatus = CoachMessageResponse["guard_status"];
export type Goal = Schemas["GoalRead"];
export type GoalList = Schemas["GoalList"];
export type GoalDetail = Schemas["GoalDetail"];
export type GoalCreate = Schemas["GoalCreate"];
export type GoalUpdate = Schemas["GoalUpdate"];
export type GoalStatus = Goal["status"];
export type GoalContribution = Schemas["GoalContributionRead"];
export type GoalContributionCreate = Schemas["GoalContributionCreate"];
export type IncomeBrief = Schemas["IncomeBrief"];
export type UnallocatedIncomeList = Schemas["UnallocatedIncomeList"];
export type PyfProposal = Schemas["PyfProposal"];
export type PyfProposalItem = Schemas["PyfProposalItem"];
export type PyfProposalRequest = Schemas["PyfProposalRequest"];
export type PyfAllocationRequest = Schemas["PyfAllocationRequest"];
export type PyfAllocationResult = Schemas["PyfAllocationResult"];
export type PyfWarning = Schemas["PyfWarning"];
export type ZoneStatus = NonNullable<BudgetZone["zone"]>;
export type ZoneMode = BudgetZone["zone_mode"];
export type AdviceVerdict = BudgetAdvice["verdict"];
export type AdviceStatus = BudgetAdvice["status"];
export type AllocationTrackingStatus = AllocationStatus["status"];
export type PaceStatus = NonNullable<AllocationStatus["pace_status"]>;
export type BudgetStrategy = Budget["strategy"];
export type BudgetStatus = Budget["status"];
export type AllocationGroup = BudgetAllocationInput["group"];
export type Direction = Transaction["direction"];
export type SpendingType = NonNullable<Transaction["spending_type"]>;
export type TransactionSource = Transaction["source"];

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
