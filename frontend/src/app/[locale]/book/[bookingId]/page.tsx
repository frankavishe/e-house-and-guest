import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { QuoteBreakdown } from "@/components/BookingWidget";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { Checkout } from "@/components/Checkout";
import { buttonClasses } from "@/components/ui/Button";
import { Link, redirect } from "@/i18n/navigation";
import { getBooking } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { formatDate, formatDateTime, formatPeriod, formatPhone, formatTZS } from "@/lib/format";

type Props = { params: Promise<{ locale: string; bookingId: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "myBookings" });
  return { title: t("title"), robots: { index: false } };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-line pt-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      {children}
    </section>
  );
}

export default async function BookingPage({ params }: Props) {
  const { locale: raw, bookingId } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: `/account/sign-in?returnTo=/book/${bookingId}`, locale });
    return null;
  }
  const booking = UUID.test(bookingId) ? await getBooking(bookingId) : null;
  if (!booking) notFound();

  const t = await getTranslations();
  const { listing, quote } = booking;
  const unit = listing.base_price?.unit;
  const pending = booking.payments.find((p) => p.status === "pending") ?? null;
  // After the first payment, lease months are paid one installment at a time.
  const installment =
    booking.status === "awaiting_payment"
      ? null
      : (booking.installments?.find((i) => i.payable) ?? null);
  const amountNow = installment?.amount_tzs ?? booking.amount_due_tzs;
  const payable =
    booking.role === "renter" &&
    (booking.can.pay || pending != null) &&
    (booking.status === "awaiting_payment" || installment != null);
  const paidOnce = booking.payments.some((p) => p.status === "succeeded");
  const isLease = listing.booking_mode === "LEASE";
  const other = booking.role === "owner" ? t("checkout.renter") : t("checkout.owner");

  return (
    <article className="mx-auto flex w-full max-w-xl flex-col gap-5">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold text-ink">
            {t("checkout.title", { code: booking.code })}
          </h1>
          <BookingStatusBadge status={booking.status} />
        </div>
        <Link href={`/l/${listing.id}`} className="font-medium text-brand-700 hover:underline">
          {listing.title}
        </Link>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">{t("checkout.period")}</dt>
          <dd className="text-ink">
            {formatPeriod(booking.period, listing.booking_mode, unit, locale)}
          </dd>
          {booking.quantity > 1 && (
            <>
              <dt className="text-muted">{t("checkout.quantity")}</dt>
              <dd className="text-ink">{booking.quantity}</dd>
            </>
          )}
        </dl>
        {booking.delivery_address && (
          <p className="text-sm text-muted">
            {t("checkout.deliveryTo", { address: booking.delivery_address })}
          </p>
        )}
      </header>

      {booking.status === "requested" && (
        <div className="rounded-xl bg-brand-50 p-4 text-sm text-brand-800">
          <p className="font-medium">
            {t("checkout.awaitingOwner", {
              time: booking.request_expires_at
                ? formatDateTime(booking.request_expires_at, locale)
                : "",
            })}
          </p>
          <p>{t("checkout.awaitingOwnerHint")}</p>
        </div>
      )}
      {booking.status === "cancelled" && (
        <div className="flex flex-col gap-2 rounded-xl border border-line p-4 text-sm">
          <p className="text-danger">{t("checkout.cancelled")}</p>
          <Link href={`/l/${listing.id}`} className="text-brand-700 hover:underline">
            {t("checkout.backToListing")}
          </Link>
        </div>
      )}
      {paidOnce && (
        <div className="flex flex-col gap-3 rounded-xl bg-brand-50 p-4 text-sm text-brand-800">
          {booking.status !== "cancelled" && (
            <p className="font-medium">{t("checkout.confirmed")}</p>
          )}
          <Link href={`/book/${booking.id}/receipt`} className={buttonClasses("secondary")}>
            {t("checkout.viewReceipt")}
          </Link>
        </div>
      )}

      {payable && (
        <section className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold text-ink">{t("checkout.amountDue")}</h2>
            <span className="text-lg font-bold tabular-nums text-ink">{formatTZS(amountNow)}</span>
          </div>
          {isLease && booking.status === "awaiting_payment" && (
            <p className="text-sm text-muted">{t("checkout.leaseFirst")}</p>
          )}
          <Checkout
            bookingId={booking.id}
            listingId={listing.id}
            amount={amountNow}
            installment={installment && { id: installment.id, seq: installment.seq }}
            paymentDueAt={booking.payment_due_at}
            defaultPhone={user.phone}
            pending={pending}
            testMode={process.env.NODE_ENV !== "production"}
          />
        </section>
      )}

      <Section title={t("booking.breakdown")}>
        <QuoteBreakdown quote={quote} />
      </Section>

      {booking.installments && booking.installments.length > 0 && (
        <Section title={t("checkout.installments")}>
          <ul className="flex flex-col gap-1 text-sm">
            {booking.installments.map((i) => (
              <li key={i.id} className="flex justify-between gap-2">
                <span className="text-muted">
                  {t("checkout.installmentRow", {
                    seq: i.seq,
                    date: formatDate(i.due_at, locale),
                  })}
                </span>
                <span className="tabular-nums">
                  {formatTZS(i.amount_tzs)} · {t(`installmentStatus.${i.status}`)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={other}>
        <p className="text-sm text-ink">{booking.counterpart.name}</p>
        <p className="text-sm text-muted">
          {booking.counterpart.phone ? (
            <a href={`tel:${booking.counterpart.phone}`} className="text-brand-700 hover:underline">
              {formatPhone(booking.counterpart.phone)}
            </a>
          ) : (
            t("checkout.phoneAfterConfirm")
          )}
        </p>
      </Section>
    </article>
  );
}
