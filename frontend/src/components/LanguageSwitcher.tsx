"use client";

import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { Link, usePathname } from "@/i18n/navigation";

/** Switches sw ⇄ en on the same page, keeping the query string (filters, dates). */
export function LanguageSwitcher() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const pathname = usePathname();
  const search = useSearchParams();
  const other = locale === "sw" ? "en" : "sw";
  const query = Object.fromEntries(search.entries());
  return (
    <Link
      href={{ pathname, query }}
      locale={other}
      hrefLang={other}
      aria-label={t("switchToLabel")}
      className="flex h-10 items-center rounded-full bg-card px-3.5 text-sm font-medium text-ink hover:bg-brand-50"
    >
      {t("switchTo")}
    </Link>
  );
}
