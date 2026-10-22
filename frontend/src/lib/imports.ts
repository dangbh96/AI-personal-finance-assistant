import {
  ApiError,
  apiUrl,
  errorMessage,
  type ColumnMapping,
  type ImportDateFormat,
  type ImportDecimalStyle,
  type ImportPreview,
  type ImportPreviewRow,
  type ImportRowStatus,
} from "@/lib/api";

/** Giới hạn khớp backend (`import_reader.MAX_IMPORT_BYTES`). */
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_IMPORT_EXTENSIONS = [".csv", ".xlsx"];
export const IMPORT_ACCEPT_ATTR = [
  ...ACCEPTED_IMPORT_EXTENSIONS,
  "text/csv",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

/** Số dòng preview hiển thị mỗi lần ("Hiện thêm"). */
export const PREVIEW_PAGE_SIZE = 100;

export const IMPORT_ROW_STATUS_LABELS: Record<ImportRowStatus, string> = {
  valid: "Hợp lệ",
  duplicate: "Trùng",
  bad: "Lỗi",
};

export const IMPORT_ROW_STATUS_CLASSES: Record<ImportRowStatus, string> = {
  valid:
    "border-emerald-300 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300",
  duplicate:
    "border-amber-300 text-amber-700 dark:border-amber-800 dark:text-amber-300",
  bad: "border-rose-300 text-rose-700 dark:border-rose-800 dark:text-rose-300",
};

export const MAPPING_FIELDS: {
  key: keyof ColumnMapping;
  label: string;
  hint: string;
}[] = [
  { key: "date", label: "Ngày giao dịch", hint: "Bắt buộc" },
  { key: "description", label: "Nội dung", hint: "Bắt buộc" },
  { key: "amount", label: "Số tiền (+/−)", hint: "Âm = chi, dương = thu" },
  { key: "debit", label: "Ghi nợ (tiền ra)", hint: "Khoản chi" },
  { key: "credit", label: "Ghi có (tiền vào)", hint: "Khoản thu" },
];

export const DATE_FORMAT_LABELS: Record<ImportDateFormat, string> = {
  "dd/mm/yyyy": "Ngày/Tháng/Năm (31/12/2026)",
  "mm/dd/yyyy": "Tháng/Ngày/Năm (12/31/2026)",
  "yyyy-mm-dd": "Năm-Tháng-Ngày (2026-12-31)",
};

export const DECIMAL_STYLE_LABELS: Record<ImportDecimalStyle, string> = {
  dot_thousands: "1.500.000 (dấu chấm ngăn nghìn)",
  comma_thousands: "1,500,000 (dấu phẩy ngăn nghìn)",
};

export const MAPPING_SOURCE_LABELS: Record<string, string> = {
  guess: "Tự đoán từ tên cột",
  profile: "Theo mapping đã lưu lần trước",
  user: "Bạn đã chỉnh",
};

export const ENCODING_LABELS: Record<string, string> = {
  "utf-8": "UTF-8",
  "utf-8-sig": "UTF-8 (có BOM)",
  cp1258: "Windows-1258",
};

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/** Kiểm tra trước khi gửi (backend vẫn kiểm tra lại). `null` = hợp lệ. */
export function validateImportFile(file: File): string | null {
  const ext = extensionOf(file.name);
  if (ext === ".xls") {
    return "File Excel cũ (.xls) chưa được hỗ trợ — bạn lưu lại dạng .xlsx hoặc .csv giúp nhé.";
  }
  if (!ACCEPTED_IMPORT_EXTENSIONS.includes(ext)) {
    return "Chỉ nhận file sao kê .csv hoặc .xlsx.";
  }
  if (file.size === 0) return "File rỗng.";
  if (file.size > MAX_IMPORT_BYTES) {
    return "File lớn hơn 10MB. Bạn tách sao kê theo tháng giúp nhé.";
  }
  return null;
}

/** Mapping đủ để chuẩn hoá chưa (backend kiểm tra lại); trả danh sách vấn đề. */
export function mappingIssues(mapping: ColumnMapping): string[] {
  const issues: string[] = [];
  if (!mapping.date) issues.push("Chưa chọn cột ngày giao dịch.");
  if (!mapping.description) issues.push("Chưa chọn cột nội dung.");
  if (!mapping.amount && !mapping.debit && !mapping.credit) {
    issues.push("Chưa chọn cột số tiền (hoặc ghi nợ / ghi có).");
  }
  if (mapping.amount && (mapping.debit || mapping.credit)) {
    issues.push(
      "Chọn cột Số tiền (+/−) hoặc cột Ghi nợ / Ghi có, không chọn cả hai.",
    );
  }
  const used = Object.values(mapping).filter(Boolean);
  if (new Set(used).size !== used.length) {
    issues.push("Một cột đang được chọn cho nhiều trường.");
  }
  return issues;
}

/** Mặc định chọn dòng hợp lệ, trừ dòng có vẻ là chuyển khoản nội bộ / có thể trùng nhập tay. */
export function selectedByDefault(row: ImportPreviewRow): boolean {
  return (
    row.status === "valid" &&
    !row.transfer_hint &&
    !row.possible_duplicate_transaction_id
  );
}

/** "Ăn Trưa" → "an trua" — lọc dòng không phân biệt dấu / hoa thường. */
export function foldText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

export function importTransactionsUrl(batchId: string): string {
  return `/transactions?source=import&import_batch_id=${batchId}`;
}

/**
 * Upload sao kê kèm tiến độ (XMLHttpRequest). Backend đọc file, đoán mapping, gợi ý danh mục —
 * kết quả chỉ là bản xem trước, chưa tạo giao dịch.
 */
export function uploadImport(
  file: File,
  bankName: string,
  onProgress: (fraction: number) => void,
): Promise<ImportPreview> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl("/imports/preview"));
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
        resolve(body as ImportPreview);
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
    if (bankName.trim()) form.append("bank_name", bankName.trim());
    xhr.send(form);
  });
}
