"use client";

import { EyeIcon, EyeOffIcon, PencilIcon, PlusIcon } from "lucide-react";
import { useState } from "react";

import { CategoryFormDialog } from "@/components/settings/category-form-dialog";
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
  apiRequest,
  describeError,
  withQuery,
  type Category,
  type CategoryUpdate,
  type Direction,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type FormState = { open: boolean; category: Category | null };

const SECTIONS: { kind: Direction; title: string; description: string }[] = [
  {
    kind: "expense",
    title: "Danh mục chi tiêu",
    description: "Loại chi tiêu mặc định được tự điền khi nhập giao dịch.",
  },
  {
    kind: "income",
    title: "Danh mục thu nhập",
    description: "Thu nhập không có loại chi tiêu.",
  },
];

export function CategoryManager() {
  const categories = useApiData<Category[]>(
    withQuery("/categories", { include_archived: true }),
  );
  const [form, setForm] = useState<FormState>({ open: false, category: null });
  const [actionError, setActionError] = useState<string | null>(null);

  async function toggleArchived(category: Category) {
    setActionError(null);
    try {
      const payload: CategoryUpdate = { is_archived: !category.is_archived };
      await apiRequest("PATCH", `/categories/${category.id}`, payload);
      categories.reload();
    } catch (err) {
      setActionError(describeError(err));
    }
  }

  const error = actionError ?? (categories.error && describeError(categories.error));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">
          Danh mục không xoá được — chỉ ẩn để giữ lịch sử giao dịch.
        </p>
        <Button onClick={() => setForm({ open: true, category: null })}>
          <PlusIcon data-icon="inline-start" />
          Thêm danh mục
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {SECTIONS.map((section) => {
        const rows = (categories.data ?? []).filter(
          (c) => c.kind === section.kind,
        );
        return (
          <Card key={section.kind}>
            <CardHeader>
              <CardTitle>{section.title}</CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              {rows.length === 0 ? (
                <p className="px-4 text-sm text-muted-foreground">
                  {categories.loading ? "Đang tải…" : "Chưa có danh mục."}
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12 pl-4" />
                      <TableHead>Tên</TableHead>
                      {section.kind === "expense" && (
                        <TableHead>Loại mặc định</TableHead>
                      )}
                      <TableHead>Trạng thái</TableHead>
                      <TableHead className="w-24" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((c) => (
                      <TableRow
                        key={c.id}
                        className={cn(c.is_archived && "text-muted-foreground")}
                      >
                        <TableCell className="pl-4 text-lg">{c.icon}</TableCell>
                        <TableCell>
                          <div className="font-medium">{c.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {c.slug}
                          </div>
                        </TableCell>
                        {section.kind === "expense" && (
                          <TableCell>
                            {c.default_spending_type && (
                              <SpendingTypeBadge value={c.default_spending_type} />
                            )}
                          </TableCell>
                        )}
                        <TableCell className="space-x-1">
                          {c.is_system && <Badge variant="outline">Mặc định</Badge>}
                          {c.is_archived && (
                            <Badge variant="secondary">Đã ẩn</Badge>
                          )}
                        </TableCell>
                        <TableCell className="pr-4 text-right">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={`Sửa ${c.name}`}
                            onClick={() => setForm({ open: true, category: c })}
                          >
                            <PencilIcon />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label={c.is_archived ? `Hiện ${c.name}` : `Ẩn ${c.name}`}
                            title={c.is_archived ? "Hiện lại" : "Ẩn"}
                            onClick={() => toggleArchived(c)}
                          >
                            {c.is_archived ? <EyeIcon /> : <EyeOffIcon />}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        );
      })}

      <CategoryFormDialog
        open={form.open}
        onOpenChange={(open) => setForm((f) => ({ ...f, open }))}
        category={form.category}
        onSaved={categories.reload}
      />
    </div>
  );
}
