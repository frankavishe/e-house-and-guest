import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { Link, redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

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
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <nav aria-label={t("title")} className="flex gap-2">
        <Link href="/admin/verifications" className="rounded-full bg-canvas px-3 py-1.5 text-sm font-medium text-ink hover:bg-brand-50">
          {t("verifications")}
        </Link>
        <Link href="/admin/listings" className="rounded-full bg-canvas px-3 py-1.5 text-sm font-medium text-ink hover:bg-brand-50">
          {t("listings")}
        </Link>
      </nav>
      {children}
    </div>
  );
}
