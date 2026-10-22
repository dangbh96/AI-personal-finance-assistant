import type { CoachGuardStatus } from "@/lib/api";

/** Câu hỏi gợi ý (phase-10 § 4.4). */
export const SUGGESTED_QUESTIONS = [
  "Tháng này khoản nào vượt budget?",
  "Tao nên giảm khoản nào?",
  "Có khoản bất thường nào không?",
  "50/30/20 là gì, có phù hợp với tao không?",
] as const;

export const MAX_MESSAGE_LENGTH = 2000;

export const GUARD_LABELS: Record<CoachGuardStatus, string> = {
  passed: "Số liệu đã đối chiếu",
  rewritten: "Đã tự sửa 1 lần cho khớp số liệu",
  fallback: "Bản tự động từ số liệu",
  refused_out_of_scope: "Ngoài phạm vi",
  refused_write_request: "Coach chỉ đọc dữ liệu",
};

export const GUARD_TONES: Record<CoachGuardStatus, string> = {
  passed:
    "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
  rewritten:
    "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300",
  fallback:
    "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
  refused_out_of_scope: "border-border bg-muted text-muted-foreground",
  refused_write_request: "border-border bg-muted text-muted-foreground",
};

/** Tên tool → mô tả tiếng Việt (tên kỹ thuật vẫn hiển thị kèm trong tool trace). */
export const TOOL_LABELS: Record<string, string> = {
  get_spending_summary: "Tổng hợp thu chi",
  get_budget_status: "Ngân sách vs thực chi",
  get_category_trend: "Xu hướng theo danh mục",
  get_budget_advice: "Tư vấn ngân sách đã có",
  get_recent_reviews: "Review gần đây",
  get_goals: "Mục tiêu tiết kiệm",
  search_transactions: "Tìm giao dịch theo ý nghĩa",
  search_knowledge: "Tra thư viện kiến thức",
  simulate: "Mô phỏng what-if",
};

const SOURCE_HEADER = /^[\s>*_#-]*nguồn[\s*_]*:?/i;

/**
 * Bỏ mục "Nguồn:" (và các dòng gạch đầu dòng ngay sau) khỏi câu trả lời khi đã hiển thị khối
 * nguồn riêng — tránh lặp.
 */
export function stripSourceSection(content: string): string {
  const lines = content.split("\n");
  const start = lines.findIndex((line) => SOURCE_HEADER.test(line));
  if (start < 0) return content;
  let end = start + 1;
  const isBullet = (line: string) => /^\s*([-*•]|\d+[.)])\s+/.test(line);
  while (end < lines.length && (lines[end].trim() === "" || isBullet(lines[end]))) {
    end += 1;
  }
  return [...lines.slice(0, start), ...lines.slice(end)].join("\n").trimEnd();
}

/** Thông báo theo mã lỗi AI của backend (`AI_*`). */
export function coachErrorHint(code: string | null): string {
  switch (code) {
    case "AI_NOT_CONFIGURED":
      return "Backend chưa cấu hình OPENAI_API_KEY nên Coach chưa trả lời được.";
    case "AI_AUTH_FAILED":
      return "OPENAI_API_KEY không hợp lệ hoặc không có quyền.";
    case "AI_RATE_LIMITED":
      return "AI đang quá tải hoặc hết hạn mức — thử lại sau ít phút.";
    case "AI_TIMEOUT":
    case "AI_UNAVAILABLE":
      return "Không kết nối được AI — thử lại sau.";
    case "AI_INVALID_OUTPUT":
      return "AI chưa trả lời được câu này — bạn thử diễn đạt khác nhé.";
    default:
      return "";
  }
}
