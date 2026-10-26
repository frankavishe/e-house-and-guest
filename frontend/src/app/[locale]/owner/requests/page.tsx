import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { RequestActions } from "@/components/RequestActions";
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
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <h1 className="text-xl font-bold text-ink">{t("requests.title")}</h1>
      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("requests.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((b) => (
            <li
              key={b.id}
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex flex-col gap-1">
                <Link href={`/book/${b.id}`} className="font-medium text-brand-700 hover:underline">
                  {b.listing.title}
                </Link>
                <p className="text-sm text-ink">
                  {formatPeriod(b.period, b.listing.booking_mode, b.listing.base_price?.unit, locale)}
                  {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
                </p>
                <p className="flex justify-between text-sm">
                  <span className="text-muted">{b.code}</span>
                  <Money amount={b.total_tzs} className="font-medium text-ink" />
                </p>
                {b.counterpart_name && (
                  <p className="text-sm text-ink">
                    {t("requests.from", { name: b.counterpart_name })}
                  </p>
                )}
                {b.request_message && (
                  <blockquote className="whitespace-pre-line rounded-lg bg-canvas p-3 text-sm text-ink">
                    {b.request_message}
                  </blockquote>
                )}
                {b.request_expires_at && (
                  <p className="text-xs text-muted">
                    {t("requests.answerBy", {
                      time: formatDateTime(b.request_expires_at, locale),
                    })}
                  </p>
                )}
              </div>
              <RequestActions bookingId={b.id} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
