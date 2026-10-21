import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";

const LINKS = [
  ["listings", "/owner/listings"],
  ["calendar", "/owner/calendar"],
  ["requests", "/owner/requests"],
  ["earnings", "/owner/earnings"],
  ["profile", "/owner/onboarding"],
] as const;

/** Tabs across the owner pages; `current` is highlighted. */
export async function OwnerNav({ current }: { current: (typeof LINKS)[number][0] }) {
  const t = await getTranslations("ownerNav");
  return (
    <nav aria-label={t("label")} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
      {LINKS.map(([key, href]) => (
        <Link
          key={key}
          href={href}
          aria-current={current === key ? "page" : undefined}
          className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
            current === key ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
          }`}
        >
          {t(key)}
        </Link>
      ))}
    </nav>
  );
}
