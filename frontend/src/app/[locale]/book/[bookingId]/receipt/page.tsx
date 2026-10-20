import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { QuoteBreakdown } from "@/components/BookingWidget";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { PrintButton } from "@/components/PrintButton";
import { Link, redirect } from "@/i18n/navigation";
import { getBooking, getReceipt } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { formatDateTime, formatPeriod, formatTZS } from "@/lib/format";

type Props = { params: Promise<{ locale: string; bookingId: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "receipt" });
  return { title: t("title"), robots: { index: false } };
}

export default async function ReceiptPage({ params }: Props) {
  const { locale: raw, bookingId } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: `/account/sign-in?returnTo=/book/${bookingId}/receipt`, locale });
    return null;
  }
  if (!UUID.test(bookingId)) notFound();
  const [{ receipt, notPaid }, booking] = await Promise.all([
    getReceipt(bookingId),
    getBooking(bookingId),
  ]);
  if (notPaid) {
    redirect({ href: `/book/${bookingId}`, locale });
    return null;
  }
  if (!receipt || !booking) notFound();

  const [t, networks] = await Promise.all([
    getTranslations("receipt"),
    getTranslations("networks"),
  ]);
  const network = (n: string) => (networks.has(n) ? networks(n) : n);
  const row = (label: string, value: string) => (
    <div className="contents">
      <dt className="text-muted">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );

  return (
    <article className="mx-auto flex w-full max-w-xl flex-col gap-5 print:max-w-none">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-ink">{t("title")}</h1>
          <p className="text-sm text-muted">
            {t("issued", { date: formatDateTime(receipt.issued_at, locale) })}
          </p>
        </div>
        <BookingStatusBadge status={receipt.status} />
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {row(t("code"), receipt.code)}
        {row(t("listing"), receipt.listing_title)}
        {row(t("owner"), receipt.owner_name)}
        {row(t("renter"), receipt.renter_name)}
        {row(
          t("period"),
          formatPeriod(
            receipt.period,
            booking.listing.booking_mode,
            booking.listing.base_price?.unit,
            locale,
          ),
        )}
        {receipt.quantity > 1 && row(t("quantity"), String(receipt.quantity))}
      </dl>

      <section className="flex flex-col gap-2 border-t border-line pt-4">
        <QuoteBreakdown quote={receipt.quote} />
      </section>

      <section className="flex flex-col gap-2 border-t border-line pt-4">
        <h2 className="text-base font-semibold text-ink">{t("payments")}</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {receipt.payments.map((p) => (
            <li key={p.id} className="flex justify-between gap-2">
              <span className="flex flex-col">
                <span className="text-ink">
                  {network(p.network)}
                  {p.confirmed_at ? ` · ${formatDateTime(p.confirmed_at, locale)}` : ""}
                </span>
                {p.provider_txn_id && (
                  <span className="text-xs text-muted">
                    {t("reference", { ref: p.provider_txn_id })}
                  </span>
                )}
              </span>
              <span className="tabular-nums text-ink">{formatTZS(p.amount_tzs)}</span>
            </li>
          ))}
        </ul>
        <dl className="flex flex-col gap-1 border-t border-line pt-2 text-sm">
          <div className="flex justify-between font-semibold">
            <dt>{t("paid")}</dt>
            <dd className="tabular-nums">{formatTZS(receipt.paid_tzs)}</dd>
          </div>
          <div className="flex justify-between text-muted">
            <dt>{t("total")}</dt>
            <dd className="tabular-nums">{formatTZS(receipt.total_tzs)}</dd>
          </div>
        </dl>
      </section>

      <div className="flex flex-wrap gap-2 print:hidden">
        <PrintButton label={t("print")} />
        <Link
          href={`/book/${bookingId}`}
          className="self-center text-sm text-brand-700 hover:underline"
        >
          {t("booking")}
        </Link>
      </div>
    </article>
  );
}
