import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { Suspense } from "react";

import { AppNav, AppNavLinks } from "@/components/app-nav";

import "./globals.css";

const fontSans = Inter({
  variable: "--font-sans",
  subsets: ["latin", "vietnamese"],
});

const fontMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Personal CFO — Trợ lý tài chính cá nhân",
  description:
    "Hiểu tiền đi đâu, lập kế hoạch chi tiêu và review định kỳ cùng AI.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      className={`${fontSans.variable} ${fontMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">
        <header className="flex h-14 items-center border-b px-6">
          <span className="font-heading text-lg font-semibold">
            Personal CFO
          </span>
          <span className="ml-3 text-sm text-muted-foreground">
            Trợ lý tài chính cá nhân
          </span>
        </header>
        <div className="flex flex-1">
          <aside className="hidden w-56 shrink-0 border-r md:block">
            {/* usePathname() là dữ liệu runtime ở route động (/reviews/weekly/[week]). */}
            <Suspense fallback={<AppNavLinks pathname="" />}>
              <AppNav />
            </Suspense>
          </aside>
          <main className="min-w-0 flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
