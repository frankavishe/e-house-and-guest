import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { PageHeader } from "@/components/ui/PageHeader";
import { RequestActions } from "@/components/RequestActions";
import { Icon } from "@/components/icons";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState } from "@/components/ui/EmptyState";
import { Link, redirect } from "@/i18n/navigation";
import { listBookings } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { formatDateTime, formatPeriod } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "requests" });
  return { title: t("title"), robots: { index: false } };
}

/** Booking requests waiting for the owner's answer (FR-018, 24 h to reply). */
export default async function OwnerRequestsPage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user?.owner_profile) {
    redirect({
      href: user ? "/owner/onboarding" : "/account/sign-in?returnTo=/owner/requests",
      locale,
    });
    return null;
  }
  const [t, result] = await Promise.all([
    getTranslations(),
    listBookings("owner", 1, 50, "requested"),
  ]);
  const items = result?.items ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("requests.title")} />
      {items.length === 0 ? (
        <EmptyState>{t("requests.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((b) => (
            <li key={b.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <Avatar name={b.counterpart_name} />
                <div className="min-w-0 flex-1">
                  {b.counterpart_name && (
                    <p className="truncate font-semibold text-ink">
                      {t("requests.from", { name: b.counterpart_name })}
                    </p>
                  )}
                  <Link
                    href={`/book/${b.id}`}
                    className="block truncate text-sm text-brand-700 hover:underline"
                  >
                    {b.listing.title}
                  </Link>
                </div>
                <Money amount={b.total_tzs} className="shrink-0 font-semibold text-ink" />
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-2xl bg-surface p-3">
                  <p className="text-xs text-muted">{b.code}</p>
                  <p className="font-medium text-ink">
                    {formatPeriod(
                      b.period,
                      b.listing.booking_mode,
                      b.listing.base_price?.unit,
                      locale,
                    )}
                    {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
                  </p>
                </div>
                {b.request_expires_at && (
                  <div className="flex items-start gap-2 rounded-2xl bg-warning-soft p-3 text-warning">
                    <Icon name="clock" className="mt-0.5 size-4 shrink-0" />
                    <p className="text-xs font-medium">
                      {t("requests.answerBy", {
                        time: formatDateTime(b.request_expires_at, locale),
                      })}
                    </p>
                  </div>
                )}
              </div>
              {b.request_message && (
                <blockquote className="whitespace-pre-line rounded-2xl rounded-tl-md bg-surface p-3 text-sm text-ink">
                  {b.request_message}
                </blockquote>
              )}
              <RequestActions bookingId={b.id} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
