"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  apiRequest,
  describeError,
  type Category,
  type CategoryCreate,
  type CategoryUpdate,
  type Direction,
  type SpendingType,
} from "@/lib/api";
import { DIRECTION_LABELS, SPENDING_TYPE_LABELS } from "@/lib/labels";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `null` = tạo mới. */
  category: Category | null;
  onSaved: () => void;
};

export function CategoryFormDialog({
  open,
  onOpenChange,
  category,
  onSaved,
}: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{category ? "Sửa danh mục" : "Thêm danh mục"}</DialogTitle>
          <DialogDescription>
            {category
              ? "Không đổi được loại Thu/Chi của danh mục đã tạo."
              : "Danh mục chi tiêu cần một loại chi tiêu mặc định để tự điền khi nhập."}
          </DialogDescription>
        </DialogHeader>
        {open && (
          <CategoryForm
            key={category?.id ?? "new"}
            category={category}
            onCancel={() => onOpenChange(false)}
            onSaved={() => {
              onSaved();
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function CategoryForm({
  category,
  onCancel,
  onSaved,
}: {
  category: Category | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(category?.name ?? "");
  const [kind, setKind] = useState<Direction>(category?.kind ?? "expense");
  const [spendingType, setSpendingType] = useState<SpendingType | null>(
    category ? category.default_spending_type : "non_essential",
  );
  const [icon, setIcon] = useState(category?.icon ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Nhập tên danh mục");
      return;
    }
    const default_spending_type = kind === "expense" ? spendingType : null;
    setSubmitting(true);
    try {
      if (category) {
        const payload: CategoryUpdate = {
          name: name.trim(),
          icon: icon.trim() || null,
          ...(kind === "expense" ? { default_spending_type } : {}),
        };
        await apiRequest("PATCH", `/categories/${category.id}`, payload);
      } else {
        const payload: CategoryCreate = {
          name: name.trim(),
          kind,
          default_spending_type,
          icon: icon.trim() || null,
        };
        await apiRequest("POST", "/categories", payload);
      }
      onSaved();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
      <div className="grid grid-cols-[1fr_5rem] gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cat-name">Tên</Label>
          <Input
            id="cat-name"
            maxLength={60}
            placeholder="Thú cưng"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cat-icon">Biểu tượng</Label>
          <Input
            id="cat-icon"
            maxLength={16}
            placeholder="🐶"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="cat-kind">Loại</Label>
        <Select
          items={DIRECTION_LABELS}
          value={kind}
          disabled={category !== null}
          onValueChange={(v) => {
            if (!v) return;
            setKind(v as Direction);
            setSpendingType(v === "expense" ? "non_essential" : null);
          }}
        >
          <SelectTrigger id="cat-kind" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(DIRECTION_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {kind === "expense" && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cat-spending-type">Loại chi tiêu mặc định</Label>
          <Select
            items={SPENDING_TYPE_LABELS}
            value={spendingType}
            onValueChange={(v) => v && setSpendingType(v as SpendingType)}
          >
            <SelectTrigger id="cat-spending-type" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(SPENDING_TYPE_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Huỷ
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Đang lưu…" : category ? "Lưu thay đổi" : "Thêm"}
        </Button>
      </DialogFooter>
    </form>
  );
}
