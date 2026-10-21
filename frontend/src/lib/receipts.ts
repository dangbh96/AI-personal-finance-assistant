import {
  ApiError,
  apiUrl,
  errorMessage,
  withQuery,
  type ReceiptDetail,
  type ReceiptStatus,
} from "@/lib/api";

/** Giới hạn khớp backend (`receipt_storage.MAX_RECEIPT_BYTES`). */
export const MAX_RECEIPT_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_RECEIPT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
];
export const ACCEPTED_RECEIPT_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".heic",
  ".heif",
];
export const RECEIPT_ACCEPT_ATTR = [
  ...ACCEPTED_RECEIPT_TYPES,
  ...ACCEPTED_RECEIPT_EXTENSIONS,
].join(",");

/** Dưới ngưỡng này backend không tạo draft hoàn chỉnh (khớp `MIN_DRAFT_CONFIDENCE`). */
export const LOW_RECEIPT_CONFIDENCE = 0.6;

export const RECEIPT_STATUS_LABELS: Record<ReceiptStatus, string> = {
  uploaded: "Đang chờ đọc",
  extracted: "Đã đọc — chờ xác nhận",
  confirmed: "Đã lưu giao dịch",
  failed: "Chưa đọc được",
};

export const RECEIPT_STATUS_CLASSES: Record<ReceiptStatus, string> = {
  uploaded: "border-border text-muted-foreground",
  extracted:
    "border-sky-300 text-sky-700 dark:border-sky-800 dark:text-sky-300",
  confirmed:
    "border-emerald-300 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300",
  failed:
    "border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300",
};

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/** Kiểm tra trước khi gửi (backend vẫn kiểm tra lại). `null` = hợp lệ. */
export function validateReceiptFile(file: File): string | null {
  const ext = extensionOf(file.name);
  // HEIC trên Windows / một số trình duyệt có type rỗng → dựa vào đuôi file.
  const typeOk =
    ACCEPTED_RECEIPT_TYPES.includes(file.type) ||
    (file.type === "" || file.type === "application/octet-stream");
  if (!ACCEPTED_RECEIPT_EXTENSIONS.includes(ext) || !typeOk) {
    return "Chỉ nhận ảnh JPEG, PNG, WEBP hoặc HEIC/HEIF — file PDF hay tài liệu khác chưa được hỗ trợ.";
  }
  if (file.size === 0) return "File ảnh rỗng.";
  if (file.size > MAX_RECEIPT_BYTES) {
    return "Ảnh lớn hơn dung lượng tối đa 10MB. Bạn chụp lại hoặc giảm kích thước ảnh giúp nhé.";
  }
  return null;
}

/** Trình duyệt đa phần không hiển thị được HEIC/HEIF → xem trước bằng ảnh backend đã đổi. */
export function canPreviewLocally(file: File): boolean {
  const ext = extensionOf(file.name);
  return ext !== ".heic" && ext !== ".heif" && !file.type.includes("hei");
}

export function receiptFileUrl(receiptId: string): string {
  return apiUrl(`/receipts/${receiptId}/file`);
}

/** 1536 → "1,5 KB", 2_500_000 → "2,4 MB" */
export function formatFileSize(bytes: number): string {
  const format = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });
  if (bytes >= 1024 * 1024) return `${format.format(bytes / 1024 / 1024)} MB`;
  if (bytes >= 1024) return `${format.format(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/**
 * Upload ảnh hoá đơn kèm tiến độ (fetch chưa có upload progress → XMLHttpRequest).
 * Backend lưu ảnh và trích xuất ngay; kết quả chỉ là draft, chưa tạo giao dịch.
 */
export function uploadReceipt(
  file: File,
  today: string,
  onProgress: (fraction: number) => void,
): Promise<ReceiptDetail> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(withQuery("/receipts", { today })));
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as ReceiptDetail);
      } else {
        reject(
          new ApiError(
            errorMessage(body, xhr.statusText || `HTTP ${xhr.status}`),
            xhr.status,
            body,
          ),
        );
      }
    };
    xhr.onerror = () => reject(new ApiError("Network error", null));
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
