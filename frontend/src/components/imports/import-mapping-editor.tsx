"use client";

import { WandSparklesIcon } from "lucide-react";
import { useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type {
  ColumnMapping,
  ImportDateFormat,
  ImportDecimalStyle,
  ImportFileInfo,
  ImportMappingInfo,
  ImportMappingUpdate,
} from "@/lib/api";
import {
  DATE_FORMAT_LABELS,
  DECIMAL_STYLE_LABELS,
  MAPPING_FIELDS,
  MAPPING_SOURCE_LABELS,
  mappingIssues,
} from "@/lib/imports";

export const NATIVE_SELECT_CLASS =
  "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30";

function normalize(mapping: ColumnMapping): ColumnMapping {
  return {
    date: mapping.date ?? null,
    description: mapping.description ?? null,
    amount: mapping.amount ?? null,
    debit: mapping.debit ?? null,
    credit: mapping.credit ?? null,
  };
}

/**
 * Bước 2: cột trong file → trường chuẩn. Cảnh báo khi thiếu ngày / nội dung / số tiền; "Áp dụng"
 * gửi `PATCH /imports/{id}/mapping` để backend chuẩn hoá lại (frontend không tự đọc file).
 */
export function ImportMappingEditor({
  fileInfo,
  mapping,
  onApply,
  applying,
  readOnly = false,
}: {
  fileInfo: ImportFileInfo;
  mapping: ImportMappingInfo;
  onApply: (update: ImportMappingUpdate) => void;
  applying: boolean;
  readOnly?: boolean;
}) {
  const idPrefix = useId();
  const [columns, setColumns] = useState<ColumnMapping>(() =>
    normalize(mapping.column_mapping),
  );
  const [dateFormat, setDateFormat] = useState<ImportDateFormat>(
    mapping.date_format,
  );
  const [decimalStyle, setDecimalStyle] = useState<ImportDecimalStyle>(
    mapping.decimal_style,
  );
  const issues = mappingIssues(columns);
  const original = normalize(mapping.column_mapping);
  const dirty =
    JSON.stringify(columns) !== JSON.stringify(original) ||
    dateFormat !== mapping.date_format ||
    decimalStyle !== mapping.decimal_style;

  return (
    <section aria-label="Mapping cột" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-heading font-semibold">Cột trong file</h3>
        <Badge variant="outline">
          <WandSparklesIcon aria-hidden />
          {MAPPING_SOURCE_LABELS[mapping.source] ?? mapping.source}
        </Badge>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {MAPPING_FIELDS.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <Label htmlFor={`${idPrefix}-${field.key}`}>{field.label}</Label>
            <select
              id={`${idPrefix}-${field.key}`}
              className={NATIVE_SELECT_CLASS}
              disabled={readOnly || applying}
              value={columns[field.key] ?? ""}
              onChange={(e) =>
                setColumns((c) => ({
                  ...c,
                  [field.key]: e.target.value || null,
                }))
              }
            >
              <option value="">— Không dùng —</option>
              {fileInfo.headers.map((header) => (
                <option key={header} value={header}>
                  {header}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">{field.hint}</span>
          </div>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-2xl">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${idPrefix}-date-format`}>Định dạng ngày</Label>
          <select
            id={`${idPrefix}-date-format`}
            className={NATIVE_SELECT_CLASS}
            disabled={readOnly || applying}
            value={dateFormat}
            onChange={(e) => setDateFormat(e.target.value as ImportDateFormat)}
          >
            {Object.entries(DATE_FORMAT_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${idPrefix}-decimal`}>Kiểu số tiền</Label>
          <select
            id={`${idPrefix}-decimal`}
            className={NATIVE_SELECT_CLASS}
            disabled={readOnly || applying}
            value={decimalStyle}
            onChange={(e) =>
              setDecimalStyle(e.target.value as ImportDecimalStyle)
            }
          >
            {Object.entries(DECIMAL_STYLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {(issues.length > 0 || (!dirty && mapping.problems.length > 0)) && (
        <ul
          role="alert"
          className="list-inside list-disc rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          {(issues.length > 0 ? issues : mapping.problems).map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <div>
          <Button
            variant={dirty ? "default" : "outline"}
            disabled={!dirty || issues.length > 0 || applying}
            onClick={() =>
              onApply({
                column_mapping: columns,
                date_format: dateFormat,
                decimal_style: decimalStyle,
              })
            }
          >
            {applying ? "Đang đọc lại…" : "Áp dụng mapping"}
          </Button>
        </div>
      )}
    </section>
  );
}
