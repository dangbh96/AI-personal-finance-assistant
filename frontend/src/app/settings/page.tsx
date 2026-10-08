import type { Metadata } from "next";

import { CategoryManager } from "@/components/settings/category-manager";

export const metadata: Metadata = { title: "Cài đặt — Personal CFO" };

export default function SettingsPage() {
  return <CategoryManager />;
}
