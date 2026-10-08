"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; phase?: number };

// Route theo docs/architecture/frontend-structure.md; mục có `phase` chưa được xây.
const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Tổng quan" },
  { href: "/transactions", label: "Giao dịch" },
  { href: "/budget", label: "Ngân sách", phase: 4 },
  { href: "/reviews/weekly", label: "Review", phase: 6 },
  { href: "/coach", label: "Financial Coach", phase: 10 },
  { href: "/goals", label: "Mục tiêu", phase: 11 },
  { href: "/settings", label: "Cài đặt" },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 p-3 text-sm">
      {NAV_ITEMS.map((item) =>
        item.phase === undefined ? (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(pathname, item.href) ? "page" : undefined}
            className={cn(
              "rounded-md px-3 py-2 font-medium hover:bg-muted",
              isActive(pathname, item.href) && "bg-muted",
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
