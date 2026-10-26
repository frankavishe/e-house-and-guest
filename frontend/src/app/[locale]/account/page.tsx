import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { DeleteAccount } from "@/components/DeleteAccount";
import { Icon, type IconName } from "@/components/icons";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { Money } from "@/components/Money";
import { SignOut } from "@/components/SignOut";
import { Avatar } from "@/components/ui/Avatar";
import { Card } from "@/components/ui/Card";
import { StatCard } from "@/components/ui/StatCard";
import { Link, redirect } from "@/i18n/navigation";
import { listBookings } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { getInbox } from "@/lib/api/social";
import { formatPeriod, formatPhone } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account" });
  return { title: t("title"), robots: { index: false } };
}

/** The signed-in user's hub: booking and message counts, recent bookings, shortcuts to the
 * owner area (or becoming an owner) and admin, and account settings. */
export default async function AccountPage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/account", locale });
    return null;
  }
  const isOwner = Boolean(user.owner_profile);
  const [t, recent, confirmed, inbox, requests] = await Promise.all([
    getTranslations(),
    listBookings("renter", 1, 4),
    listBookings("renter", 1, 1, "confirmed"),
    getInbox(1, 1),
    isOwner ? listBookings("owner", 1, 1, "requested") : Promise.resolve(null),
  ]);

  const links: [string, string, string, IconName][] = [
    ["/account/bookings", t("account.bookings"), t("account.bookingsHint"), "calendar"],
    ["/account/messages", t("account.messages"), t("account.messagesHint"), "message"],
    isOwner
      ? ["/owner/listings", t("account.ownerArea"), t("account.ownerAreaHint"), "building"]
      : ["/owner/onboarding", t("account.becomeOwner"), t("account.becomeOwnerHint"), "building"],
  ];
  if (isOwner)
    links.push(["/owner/requests", t("account.requests"), t("account.requestsHint"), "inbox"]);
  if (user.roles.includes("admin"))
    links.push(["/admin/stats", t("account.admin"), t("account.adminHint"), "shield"]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="sr-only">{t("account.title")}</h1>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={t("shell.statBookings")} value={recent?.total ?? 0} icon="calendar" />
        <StatCard
          label={t("shell.statConfirmed")}
          value={confirmed?.total ?? 0}
          icon="checkCircle"
        />
        <StatCard label={t("shell.statUnread")} value={inbox?.unread_total ?? 0} icon="message" />
        {requests ? (
          <StatCard label={t("shell.statRequests")} value={requests.total} icon="inbox" />
        ) : (
          <Link
            href="/owner/onboarding"
            className="flex flex-col justify-between gap-3 rounded-[var(--radius-card)] bg-hero p-5 text-white"
          >
            <span className="text-sm font-medium">{t("account.becomeOwner")}</span>
            <span className="flex items-center justify-between gap-2 text-xs text-white/85">
              {t("account.becomeOwnerHint")}
              <Icon name="arrowRight" className="size-5 shrink-0" />
            </span>
          </Link>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card
          title={t("shell.recentBookings")}
          action={
            <Link href="/account/bookings" className="text-muted hover:text-brand-700">
              {t("shell.viewAll")} ›
            </Link>
          }
        >
          {(recent?.items.length ?? 0) === 0 ? (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-muted">{t("myBookings.empty")}</p>
              <Link href="/search" className="text-sm font-medium text-brand-700 hover:underline">
                {t("myBookings.find")}
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {recent!.items.map((b) => (
                <li key={b.id}>
                  <Link
                    href={`/book/${b.id}`}
                    className="flex items-center gap-3 rounded-2xl bg-surface p-2.5 transition-colors hover:bg-brand-50"
                  >
                    <ImageWithFallback
                      src={b.listing.cover_photo?.url_320}
                      alt={b.listing.cover_photo?.alt ?? b.listing.title}
                      fallbackLabel={t("common.imageUnavailable")}
                      sizes="56px"
                      className="size-14 shrink-0 rounded-xl"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink">{b.listing.title}</p>
                      <p className="truncate text-xs text-muted">
                        {formatPeriod(
                          b.period,
                          b.listing.booking_mode,
                          b.listing.base_price?.unit,
                          locale,
                        )}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <BookingStatusBadge status={b.status} />
                      <Money amount={b.total_tzs} className="text-xs font-medium text-ink" />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card title={t("shell.quickLinks")}>
            <ul className="flex flex-col gap-2">
              {links.map(([href, label, hint, icon]) => (
                <li key={href}>
                  <Link
                    href={href}
                    className="group flex items-center gap-3 rounded-2xl bg-surface p-3 transition-colors hover:bg-brand-50"
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                      <Icon name={icon} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-ink">{label}</span>
                      <span className="block truncate text-xs text-muted">{hint}</span>
                    </span>
                    <Icon
                      name="chevronRight"
                      className="ml-auto size-4 shrink-0 text-muted group-hover:text-brand-700"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>

          <Card title={t("shell.settings")}>
            <div className="mb-4 flex items-center gap-3">
              <Avatar name={user.name} />
              <div className="min-w-0">
                <p className="truncate font-semibold">{user.name ?? t("account.title")}</p>
                <p className="text-sm text-muted">{formatPhone(user.phone)}</p>
              </div>
            </div>
            <div className="flex flex-col gap-4">
              <SignOut />
              <DeleteAccount />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
