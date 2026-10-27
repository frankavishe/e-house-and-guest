import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { QuoteBreakdown } from "@/components/BookingWidget";
import { BookingProgress } from "@/components/BookingProgress";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { CancelBooking } from "@/components/CancelBooking";
import { Checkout } from "@/components/Checkout";
import { ClaimForm } from "@/components/ClaimForm";
import { RefundActions } from "@/components/RefundActions";
import { RequestActions } from "@/components/RequestActions";
import { ReviewForm } from "@/components/ReviewForm";
import { buttonClasses } from "@/components/ui/Button";
import { Link, redirect } from "@/i18n/navigation";
import { getBooking } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { formatDate, formatDateTime, formatPeriod, formatPhone, formatTZS } from "@/lib/format";

type Props = { params: Promise<{ locale: string; bookingId: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, bookingId } = await params;
  const t = await getTranslations({ locale });
  const booking = UUID.test(bookingId) ? await getBooking(bookingId) : null;
  return {
    title: booking ? t("checkout.title", { code: booking.code }) : t("myBookings.title"),
    robots: { index: false },
  };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
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
  const requestDeadline = booking.request_expires_at
    ? formatDateTime(booking.request_expires_at, locale)
    : "";
  const payable =
    booking.role === "renter" &&
    (booking.can.pay || pending != null) &&
    (booking.status === "awaiting_payment" || installment != null);
  const paidOnce = booking.payments.some((p) => p.status === "succeeded");
  const isLease = listing.booking_mode === "LEASE";
  const other = booking.role === "owner" ? t("checkout.renter") : t("checkout.owner");
  const openClaim = booking.claims.find((c) => c.status === "open") ?? null;

  return (
    <article className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <header className="relative flex flex-col gap-4 overflow-hidden rounded-[var(--radius-card)] bg-hero p-5 text-white sm:p-6">
        <span
          aria-hidden
          className="pointer-events-none absolute -right-12 -top-12 size-44 rounded-full border-[22px] border-white/10"
        />
        <div className="relative flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("checkout.title", { code: booking.code })}
          </h1>
          <span className="rounded-full bg-white px-1 py-0.5">
            <BookingStatusBadge status={booking.status} />
          </span>
        </div>
        <Link
          href={`/l/${listing.id}`}
          className="relative w-fit text-lg font-medium text-white/95 underline-offset-4 hover:underline"
        >
          {listing.title}
        </Link>
        <dl className="relative grid gap-2 sm:grid-cols-2">
          <div className="rounded-2xl bg-white/15 p-3 backdrop-blur">
            <dt className="text-xs text-white/75">{t("checkout.period")}</dt>
            <dd className="mt-0.5 font-medium">
              {formatPeriod(booking.period, listing.booking_mode, unit, locale)}
            </dd>
          </div>
          {booking.quantity > 1 && (
            <div className="rounded-2xl bg-white/15 p-3 backdrop-blur">
              <dt className="text-xs text-white/75">{t("checkout.quantity")}</dt>
              <dd className="mt-0.5 font-medium">{booking.quantity}</dd>
            </div>
          )}
          {booking.delivery_address && (
            <div className="rounded-2xl bg-white/15 p-3 backdrop-blur sm:col-span-2">
              <dd className="text-sm">
                {t("checkout.deliveryTo", { address: booking.delivery_address })}
              </dd>
            </div>
          )}
        </dl>
      </header>

      {!["cancelled", "disputed"].includes(booking.status) && (
        <div className="rounded-[var(--radius-card)] bg-card p-5">
          <BookingProgress
            status={booking.status}
            wasRequested={booking.request_expires_at != null || booking.request_message != null}
          />
        </div>
      )}

      {booking.status === "requested" && (
        <div className="flex flex-col gap-3 rounded-2xl bg-brand-50 p-4 text-sm text-brand-700">
          {booking.can.accept ? (
            <p className="font-medium">{t("requests.ownerPrompt", { time: requestDeadline })}</p>
          ) : (
            <div>
              <p className="font-medium">
                {t("checkout.awaitingOwner", { time: requestDeadline })}
              </p>
              <p>{t("checkout.awaitingOwnerHint")}</p>
            </div>
          )}
          {booking.request_message && (
            <div className="flex flex-col gap-1">
              <p className="text-xs text-muted">
                {t(booking.role === "renter" ? "requests.yourMessage" : "requests.renterMessage")}
              </p>
              <blockquote className="whitespace-pre-line rounded-2xl bg-surface p-3 text-ink">
                {booking.request_message}
              </blockquote>
            </div>
          )}
          {booking.can.accept && <RequestActions bookingId={booking.id} />}
        </div>
      )}
      {booking.status === "cancelled" && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-card)] bg-card p-4 text-sm">
          <p className="text-danger">
            {booking.cancelled_by
              ? t(
                  booking.cancelled_by === booking.role
                    ? "cancel.by_you"
                    : `cancel.by_${booking.cancelled_by}`,
                )
              : t("checkout.cancelled")}
          </p>
          {booking.cancel_reason && (
            <p className="text-muted">
              {t("cancel.reasonShown", { reason: booking.cancel_reason })}
            </p>
          )}
          <Link href={`/l/${listing.id}`} className="text-brand-700 hover:underline">
            {t("checkout.backToListing")}
          </Link>
        </div>
      )}
      {openClaim && (
        <p className="rounded-2xl bg-warning-soft p-4 text-sm text-warning">
          {t("claim.disputedBanner")}
        </p>
      )}
      {paidOnce && (
        <div className="flex flex-col gap-3 rounded-2xl bg-brand-50 p-4 text-sm text-brand-700">
          {booking.status !== "cancelled" && booking.status !== "disputed" && (
            <p className="font-medium">{t("checkout.confirmed")}</p>
          )}
          <Link href={`/book/${booking.id}/receipt`} className={buttonClasses("secondary")}>
            {t("checkout.viewReceipt")}
          </Link>
        </div>
      )}

      {payable && (
        <section className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold text-ink">{t("checkout.amountDue")}</h2>
            <span className="text-2xl font-semibold tabular-nums tracking-tight text-ink">
              {formatTZS(amountNow)}
            </span>
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

      {booking.refunds.length > 0 && (
        <Section title={t("refunds.title")}>
          <ul className="flex flex-col gap-3 text-sm">
            {booking.refunds.map((r) => (
              <li key={r.id} className="flex flex-col gap-2">
                <div className="flex justify-between gap-2">
                  <span className="text-muted">
                    {t(`refunds.reason_${r.reason}`)} · {formatDate(r.created_at, locale)}
                  </span>
                  <span className="tabular-nums">
                    {formatTZS(r.amount_tzs)} · {t(`refunds.status_${r.status}`)}
                  </span>
                </div>
                {booking.role === "admin" && r.status === "failed" && <RefundActions id={r.id} />}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(booking.claims.length > 0 || booking.can.claim) && (
        <Section title={t("claim.title")}>
          {booking.claims.map((c) => (
            <div
              key={c.id}
              className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-3 text-sm"
            >
              <p className="font-medium text-ink">
                {t(`claim.kind_${c.kind}`)} · {t(`claim.status_${c.status}`)}
              </p>
              <p className="text-muted">
                {t(`claim.openedBy_${c.opened_by}`)} · {formatDate(c.created_at, locale)}
              </p>
              <p className="whitespace-pre-line text-ink">{c.description}</p>
              {c.amount_claimed_tzs != null && (
                <p className="text-muted">
                  {t("claim.claimed", { amount: formatTZS(c.amount_claimed_tzs) })}
                </p>
              )}
              {c.resolution && (
                <p className="text-ink">
                  {t(`claim.resolution_${c.resolution}`)}
                  {c.amount_awarded_tzs
                    ? ` · ${t("claim.awarded", { amount: formatTZS(c.amount_awarded_tzs) })}`
                    : ""}
                </p>
              )}
            </div>
          ))}
          {booking.can.claim && (
            <ClaimForm bookingId={booking.id} canClaimDamage={booking.role === "owner"} />
          )}
        </Section>
      )}

      <Section title={other}>
        <p className="text-sm text-ink">{booking.counterpart.name}</p>
        <p className="text-sm text-muted">
          {booking.counterpart.phone ? (
            <a href={`tel:${booking.counterpart.phone}`} className="text-brand-700 hover:underline">
              {formatPhone(booking.counterpart.phone)}
            </a>
          ) : booking.status === "cancelled" ? null : (
            t("checkout.phoneAfterConfirm")
          )}
        </p>
      </Section>

      {booking.can.review && booking.role !== "admin" && (
        <Section title={t("reviews.title")}>
          <ReviewForm
            bookingId={booking.id}
            about={booking.role === "renter" ? "listing" : "renter"}
          />
        </Section>
      )}

      {booking.can.cancel && booking.role !== "admin" && (
        <Section title={t("cancel.title")}>
          <p className="text-sm text-muted">
            {t("cancel.policyLine", { policy: t(`policy.${booking.cancellation_policy}`) })}
          </p>
          <CancelBooking bookingId={booking.id} />
        </Section>
      )}
    </article>
  );
}
