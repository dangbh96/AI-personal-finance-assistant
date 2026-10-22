"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; phase?: number; match?: string };

// Route theo docs/architecture/frontend-structure.md; mục có `phase` chưa được xây.
const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Tổng quan" },
  { href: "/transactions", label: "Giao dịch" },
  { href: "/import", label: "Nhập dữ liệu" },
  { href: "/budget", label: "Ngân sách" },
  { href: "/reviews/weekly", label: "Review", match: "/reviews" },
  { href: "/coach", label: "Financial Coach" },
  { href: "/goals", label: "Mục tiêu" },
  { href: "/calendar", label: "Lịch dòng tiền" },
  { href: "/settings", label: "Cài đặt" },
];

function isActive(pathname: string, item: NavItem): boolean {
  const prefix = item.match ?? item.href;
  return prefix === "/" ? pathname === "/" : pathname.startsWith(prefix);
}

export function AppNav() {
  return <AppNavLinks pathname={usePathname()} />;
}

/** Danh sách link; `pathname` rỗng = chưa biết route (fallback khi đang stream). */
export function AppNavLinks({ pathname }: { pathname: string }) {
  return (
    <nav className="flex flex-col gap-1 p-3 text-sm">
      {NAV_ITEMS.map((item) =>
        item.phase === undefined ? (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(pathname, item) ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-2 font-medium hover:bg-muted",
              isActive(pathname, item) && "bg-muted",
            )}
          >
            {item.label}
          </Link>
        ) : (
          <span
            key={item.href}
            aria-disabled="true"
            title={`Có từ Phase ${item.phase}`}
            className="flex items-center justify-between rounded-md px-3 py-2 text-muted-foreground"
          >
            {item.label}
            <span className="text-xs">P{item.phase}</span>
          </span>
        ),
      )}
    </nav>
  );
}
