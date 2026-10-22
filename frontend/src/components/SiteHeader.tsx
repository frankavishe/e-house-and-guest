import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { NotificationBell } from "./NotificationBell";

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
            <>
              <Link
                href="/account/messages"
                title={t("nav.messages")}
                aria-label={t("nav.messages")}
                className="rounded-md p-2 text-ink hover:bg-canvas"
              >
                <svg
                  aria-hidden
                  viewBox="0 0 24 24"
                  className="size-5"
                  fill="none"
                  stroke="currentColor"
                >
                  <path
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
                  />
                </svg>
              </Link>
              <NotificationBell />
              <Link
                href="/account"
                title={t("nav.account")}
                className="max-w-32 truncate rounded-md px-2 py-1 text-sm text-ink hover:bg-canvas"
              >
                {user.name ?? t("nav.account")}
              </Link>
            </>
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
