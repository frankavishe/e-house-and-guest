import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { ClientMessages } from "@/i18n/ClientMessages";
import { Link, redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

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

/** Admin area: signed-out visitors go to sign-in; signed-in non-admins get a 404. The API
 * enforces the same rule on every admin route. */
export default async function AdminLayout({ children, params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/admin/verifications", locale });
    return null;
  }
  if (!user.roles.includes("admin")) notFound();
  const t = await getTranslations("admin");

  return (
    <ClientMessages section="admin">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        <nav aria-label={t("title")} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          {SECTIONS.map((section) => (
            <Link
              key={section}
              href={`/admin/${section}`}
              className="shrink-0 rounded-full bg-canvas px-3 py-1.5 text-sm font-medium text-ink hover:bg-brand-50"
            >
              {t(section)}
            </Link>
          ))}
        </nav>
        {children}
      </div>
    </ClientMessages>
  );
}
