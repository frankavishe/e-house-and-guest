import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Logo } from "./shell/Logo";
import { ThemeToggle } from "./ThemeToggle";

const NETWORKS = ["M-Pesa", "Mixx", "Airtel Money", "HaloPesa"];

export async function SiteFooter() {
  const t = await getTranslations();
  const link = "text-sm text-muted hover:text-ink";
  return (
    <footer className="mx-auto max-w-6xl px-4 pb-10 pt-8 sm:px-6">
      <div className="grid gap-8 sm:grid-cols-[2fr_1fr_1fr]">
        <div className="flex flex-col gap-3">
          <Logo name={t("common.appName")} />
          <p className="max-w-sm text-sm text-muted">{t("footer.about")}</p>
          <div className="flex flex-wrap items-center gap-1.5" aria-label={t("footer.pay")}>
            {NETWORKS.map((n) => (
              <span key={n} className="rounded-full bg-surface px-2.5 py-1 text-xs font-medium text-ink">
                {n}
              </span>
            ))}
          </div>
        </div>
        <nav aria-label={t("footer.explore")} className="flex flex-col gap-2">
          <p className="text-sm font-semibold">{t("footer.explore")}</p>
          <Link href="/" className={link}>
            {t("nav.home")}
          </Link>
          <Link href="/search" className={link}>
            {t("shell.browse")}
          </Link>
          <Link href="/account/bookings" className={link}>
            {t("nav.myBookings")}
          </Link>
        </nav>
        <nav aria-label={t("footer.forOwners")} className="flex flex-col gap-2">
          <p className="text-sm font-semibold">{t("footer.forOwners")}</p>
          <Link href="/owner/onboarding" className={link}>
            {t("footer.listYours")}
          </Link>
          <Link href="/owner/listings" className={link}>
            {t("footer.ownerHome")}
          </Link>
        </nav>
      </div>
      <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
        <p className="text-xs text-muted">{t("footer.rights", { year: new Date().getFullYear() })}</p>
        <ThemeToggle className="w-48" />
      </div>
    </footer>
  );
}
