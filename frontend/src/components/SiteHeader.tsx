import { getTranslations } from "next-intl/server";
import { Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { Icon } from "./icons";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { NotificationBell } from "./NotificationBell";
import { ThemeIconButton } from "./ThemeToggle";
import { Logo } from "./shell/Logo";
import { Avatar } from "./ui/Avatar";
import { buttonClasses } from "./ui/Button";

export async function SiteHeader() {
  const [t, user] = await Promise.all([getTranslations(), getCurrentUser()]);
  const iconButton =
    "flex size-10 items-center justify-center rounded-full bg-card text-ink hover:bg-brand-50";
  return (
    <header className="sticky top-0 z-10 bg-surface/95 backdrop-blur-md sm:rounded-t-[var(--radius-shell)]">
      <div className="flex h-16 items-center justify-between gap-2 px-4 sm:h-20 sm:px-6 lg:px-8">
        <Logo name={t("common.appName")} className="min-w-0" />
        <nav className="flex items-center gap-2">
          <Suspense fallback={null}>
            <LanguageSwitcher />
          </Suspense>
          <Link
            href="/search"
            aria-label={t("shell.search")}
            title={t("shell.search")}
            className={`${iconButton} max-sm:hidden`}
          >
            <Icon name="search" />
          </Link>
          <ThemeIconButton className={`${iconButton} max-sm:hidden`} />
          {user ? (
            <>
              <Link
                href="/account/messages"
                title={t("nav.messages")}
                aria-label={t("nav.messages")}
                className={`${iconButton} max-sm:hidden`}
              >
                <Icon name="message" />
              </Link>
              <NotificationBell />
              <Link
                href="/account"
                title={t("nav.account")}
                className="flex items-center gap-2 rounded-full bg-card py-1 pl-1 pr-1 text-sm font-medium text-ink hover:bg-brand-50 sm:pr-3"
              >
                <Avatar name={user.name} size="sm" />
                <span className="max-w-28 truncate max-sm:sr-only">
                  {user.name ?? t("nav.account")}
                </span>
              </Link>
            </>
          ) : (
            <Link href="/account/sign-in" className={buttonClasses("primary", "md")}>
              {t("nav.signIn")}
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
