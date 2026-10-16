import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { LanguageSwitcher } from "./LanguageSwitcher";

export async function SiteHeader() {
  const [t, user] = await Promise.all([getTranslations(), getCurrentUser()]);
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-2 px-4">
        <Link href="/" className="text-base font-bold text-brand-800">
          {t("common.appName")}
        </Link>
        <nav className="flex items-center gap-1">
          <Suspense fallback={null}>
            <LanguageSwitcher />
          </Suspense>
          {user ? (
            <span className="max-w-32 truncate rounded-md px-2 py-1 text-sm text-ink">
              {user.name ?? t("nav.account")}
            </span>
          ) : (
            <Link
              href="/account/sign-in"
              className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
            >
              {t("nav.signIn")}
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
