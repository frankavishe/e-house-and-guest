"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";

const SECTIONS = [
  "verifications",
  "listings",
  "bookings",
  "claims",
  "payouts",
  "reports",
  "users",
  "categories",
  "stats",
] as const;

/** Tabs across the admin pages; the current section is highlighted. */
export function AdminNav() {
  const t = useTranslations("admin");
  const pathname = usePathname();
  return (
    <nav aria-label={t("title")} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
      {SECTIONS.map((section) => {
        const href = `/admin/${section}`;
        const current = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={section}
            href={href}
            aria-current={current ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
              current ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
            }`}
          >
            {t(section)}
          </Link>
        );
      })}
    </nav>
  );
}
