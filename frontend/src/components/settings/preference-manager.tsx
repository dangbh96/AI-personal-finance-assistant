"use client";

import { SparklesIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { SpendingTypeBadge } from "@/components/spending-type-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApiData } from "@/hooks/use-api-data";
import {
  ApiError,
  apiRequest,
  describeError,
  type Category,
  type Preference,
  type PreferenceCreate,
  type PreferenceDraft,
  type PreferenceList,
  type PreferenceParseRequest,
  type SpendingType,
} from "@/lib/api";
import { describePreference, SPENDING_TYPE_LABELS } from "@/lib/labels";

function formatLocalDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN");
}

/** `/settings` → tab "Sở thích phân loại": dạy AI bằng câu + xem/xoá preference đã học. */
export function PreferenceManager() {
  const preferences = useApiData<PreferenceList>("/classification-preferences");
  const categories = useApiData<Category[]>("/categories");
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function remove(preference: Preference) {
    setActionError(null);
    setNotice(null);
    try {
      await apiRequest("DELETE", `/classification-preferences/${preference.id}`);
      setNotice(`Đã xoá sở thích ${describePreference(preference)}.`);
      preferences.reload();
    } catch (err) {
      setActionError(describeError(err));
    }
  }

  const items = preferences.data?.items ?? [];
  const error =
    actionError ?? (preferences.error && describeError(preferences.error));

  return (
    <div className="flex flex-col gap-6">
      <PreferenceStatementBox
        categories={categories.data ?? []}
        onSaved={(preference) => {
          setActionError(null);
          setNotice(`Đã lưu sở thích ${describePreference(preference)}.`);
          preferences.reload();
        }}
      />

      <Card>
        <CardHeader>
          <CardTitle>Sở thích đã học</CardTitle>
          <CardDescription>
            AI học khi bạn sửa danh mục / loại chi tiêu của bản nháp rồi lưu.
            Lần sau câu có cùng từ khoá sẽ được phân loại theo cách của bạn. Xoá
            một dòng nếu AI học sai.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 px-0">
          {(error || notice) && (
            <p
              role={error ? "alert" : "status"}
              className={`px-4 text-sm ${error ? "text-destructive" : ""}`}
            >
              {error ?? notice}
            </p>
          )}
          {items.length === 0 ? (
            <p className="px-4 text-sm text-muted-foreground">
              {preferences.loading
                ? "Đang tải…"
                : "Chưa có sở thích nào. Hãy sửa phân loại của một bản nháp khi nhập nhanh, hoặc dạy AI bằng câu ở trên."}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Từ khoá</TableHead>
                  <TableHead>Danh mục</TableHead>
                  <TableHead>Loại chi tiêu</TableHead>
                  <TableHead className="text-right">Số lần dùng</TableHead>
                  <TableHead>Dùng gần nhất</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="pl-4">
                      <div className="font-mono font-medium">{p.pattern}</div>
                      <div
                        className="max-w-64 truncate text-xs text-muted-foreground"
                        title={p.example_text}
                      >
                        {p.example_text}
                      </div>
                    </TableCell>
                    <TableCell>
                      {p.category.icon} {p.category.name}
                    </TableCell>
                    <TableCell>
                      {p.spending_type ? (
                        <SpendingTypeBadge value={p.spending_type} />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {p.hit_count}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {p.last_used_at ? formatLocalDate(p.last_used_at) : "—"}
                    </TableCell>
                    <TableCell className="pr-4 text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Xoá sở thích ${p.pattern}`}
                        title="Xoá"
                        onClick={() => remove(p)}
                      >
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

type DraftValues = {
  pattern: string;
  categoryId: string | null;
  spendingType: SpendingType | null;
};

/** Nhập câu "Tao coi giày là thiết yếu" → AI tạo draft → user sửa/xác nhận rồi mới lưu. */
function PreferenceStatementBox({
  categories,
  onSaved,
}: {
  categories: Category[];
  onSaved: (preference: Preference) => void;
}) {
  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<PreferenceDraft | null>(null);
  const [values, setValues] = useState<DraftValues | null>(null);

  async function handleParse(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = text.trim();
    if (!input || parsing) return;
    setParsing(true);
    setError(null);
    try {
      const result = await apiRequest<PreferenceDraft>(
        "POST",
        "/classification-preferences/parse",
        { text: input } satisfies PreferenceParseRequest,
      );
      setDraft(result);
      setValues({
        pattern: result.pattern,
        categoryId: result.category_id,
        spendingType: result.spending_type ?? null,
      });
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "AI_NOT_CONFIGURED"
          ? "Chưa cấu hình AI nên chưa phân tích được câu. Bạn vẫn có thể dạy AI bằng cách sửa phân loại khi nhập nhanh."
          : describeError(err),
      );
    } finally {
      setParsing(false);
    }
  }

  function reset() {
    setDraft(null);
    setValues(null);
  }

  async function handleSave() {
    if (!draft || !values) return;
    const category = categories.find((c) => c.id === values.categoryId);
    if (!values.pattern.trim() || !category) {
      setError("Cần từ khoá và danh mục.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await apiRequest<Preference>(
        "POST",
        "/classification-preferences",
        {
          pattern: values.pattern.trim(),
          category_slug: category.slug,
          spending_type: category.kind === "expense" ? values.spendingType : null,
          example_text: draft.example_text,
        } satisfies PreferenceCreate,
      );
      reset();
      setText("");
      onSaved(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const category = categories.find((c) => c.id === values?.categoryId);
  const categoryItems = Object.fromEntries(
    categories.map((c) => [c.id, `${c.icon ?? ""} ${c.name}`.trim()]),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SparklesIcon className="size-4 text-violet-500" aria-hidden />
          Dạy AI cách bạn phân loại
        </CardTitle>
        <CardDescription>
          Ví dụ: “Tao coi giày là thiết yếu”, “Sửa laptop là bất thường”. AI chỉ
          tạo bản nháp — bạn kiểm tra rồi mới lưu.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form onSubmit={handleParse} className="flex gap-2">
          <Input
            aria-label="Câu sở thích phân loại"
            placeholder="Tao coi giày là thiết yếu"
            maxLength={300}
            autoComplete="off"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={parsing}
          />
          <Button type="submit" disabled={parsing || !text.trim()}>
            {parsing ? "Đang phân tích…" : "Phân tích"}
          </Button>
        </form>

        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        {draft && values && (
          <section
            aria-label="Bản nháp sở thích"
            className="flex flex-col gap-4 rounded-lg border p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-xs text-muted-foreground">💡 {draft.reason}</p>
              <Badge variant="outline">
                Độ tin cậy {Math.round(draft.confidence * 100)}%
              </Badge>
            </div>

            {draft.warnings.length > 0 && (
              <ul className="flex flex-col gap-1 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                {draft.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}

            <fieldset
              disabled={saving}
              className="grid gap-3 sm:grid-cols-3"
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pref-pattern">Từ khoá</Label>
                <Input
                  id="pref-pattern"
                  maxLength={100}
                  value={values.pattern}
                  onChange={(e) =>
                    setValues({ ...values, pattern: e.target.value })
                  }
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pref-category">Danh mục</Label>
                <Select
                  items={categoryItems}
                  value={values.categoryId}
                  onValueChange={(v) => {
                    const next = categories.find((c) => c.id === v);
                    setValues({
                      ...values,
                      categoryId: (v as string | null) ?? null,
                      spendingType:
                        next?.kind === "expense"
                          ? (next.default_spending_type ?? null)
                          : null,
                    });
                  }}
                >
                  <SelectTrigger id="pref-category" className="w-full">
                    <SelectValue placeholder="Chọn danh mục" />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {categoryItems[c.id]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {category?.kind === "expense" && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="pref-spending-type">Loại chi tiêu</Label>
                  <Select
                    items={SPENDING_TYPE_LABELS}
                    value={values.spendingType}
                    onValueChange={(v) =>
                      v &&
                      setValues({ ...values, spendingType: v as SpendingType })
                    }
                  >
                    <SelectTrigger id="pref-spending-type" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(SPENDING_TYPE_LABELS).map(
                        ([value, label]) => (
                          <SelectItem key={value} value={value}>
                            {label}
                          </SelectItem>
                        ),
                      )}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </fieldset>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={reset} disabled={saving}>
                Bỏ qua
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Đang lưu…" : "Lưu sở thích"}
              </Button>
            </div>
          </section>
        )}
      </CardContent>
    </Card>
  );
}
