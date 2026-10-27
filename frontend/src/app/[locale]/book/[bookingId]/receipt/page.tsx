import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { QuoteBreakdown } from "@/components/BookingWidget";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { PrintButton } from "@/components/PrintButton";
import { Icon } from "@/components/icons";
import { InfoTiles } from "@/components/ui/InfoTiles";
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
  return (
    <article className="mx-auto flex w-full max-w-xl flex-col gap-5 print:max-w-none">
      <header className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-hero p-6 text-white print:border print:border-line print:bg-none print:text-ink">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
            <p className="text-sm text-white/80 print:text-muted">
              {t("issued", { date: formatDateTime(receipt.issued_at, locale) })}
            </p>
          </div>
          <BookingStatusBadge status={receipt.status} />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <p className="font-mono text-sm text-white/80 print:text-muted">{receipt.code}</p>
          <div className="text-right">
            <p className="text-xs text-white/80 print:text-muted">{t("paid")}</p>
            <p className="text-3xl font-semibold tabular-nums tracking-tight">
              {formatTZS(receipt.paid_tzs)}
            </p>
          </div>
        </div>
      </header>

      <section className="rounded-[var(--radius-card)] bg-card p-5">
        <InfoTiles
          tiles={[
            { label: t("code"), value: receipt.code, mono: true },
            { label: t("listing"), value: receipt.listing_title, wide: true },
            { label: t("owner"), value: receipt.owner_name },
            { label: t("renter"), value: receipt.renter_name },
            {
              label: t("period"),
              value: formatPeriod(
                receipt.period,
                booking.listing.booking_mode,
                booking.listing.base_price?.unit,
                locale,
              ),
              wide: true,
            },
            receipt.quantity > 1 && { label: t("quantity"), value: String(receipt.quantity) },
          ]}
        />
      </section>

      <section className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5">
        <QuoteBreakdown quote={receipt.quote} />
      </section>

      <section className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5">
        <h2 className="text-lg font-semibold text-ink">{t("payments")}</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {receipt.payments.map((p) => (
            <li key={p.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-surface print:hidden">
                <Icon name="wallet" className="size-5" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="font-medium text-ink">{network(p.network)}</span>
                <span className="truncate text-xs text-muted">
                  {[
                    p.confirmed_at && formatDateTime(p.confirmed_at, locale),
                    p.provider_txn_id && t("reference", { ref: p.provider_txn_id }),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </span>
              <span className="shrink-0 font-semibold tabular-nums text-ink">
                {formatTZS(p.amount_tzs)}
              </span>
            </li>
          ))}
        </ul>
        <dl className="flex flex-col gap-1 border-t border-line pt-3 text-sm">
          <div className="flex justify-between font-semibold text-ink">
            <dt>{t("paid")}</dt>
            <dd className="tabular-nums">{formatTZS(receipt.paid_tzs)}</dd>
          </div>
          {receipt.total_tzs > receipt.paid_tzs && (
            <div className="flex justify-between text-muted">
              <dt>{t("balance")}</dt>
              <dd className="tabular-nums">{formatTZS(receipt.total_tzs - receipt.paid_tzs)}</dd>
            </div>
          )}
        </dl>
      </section>

      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <PrintButton label={t("print")} />
        <Link
          href={`/book/${bookingId}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
        >
          {t("booking")}
          <Icon name="chevronRight" className="size-4" />
        </Link>
      </div>
    </article>
  );
}
