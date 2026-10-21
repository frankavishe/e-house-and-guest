import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { addDays } from "@/components/ListingAvailability";
import { BlockForm, RemoveBlockButton } from "@/components/OwnerCalendarActions";
import { OwnerNav } from "@/components/OwnerNav";
import { Link, redirect } from "@/i18n/navigation";
import { getOwnerCalendar, getOwnerListing } from "@/lib/api/owner";
import { getCurrentUser } from "@/lib/api/server";
import { eatDateString, formatDate } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ listing?: string; month?: string }>;
};

type Span = { start: string; end: string };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "calendar" });
  return { title: t("title"), robots: { index: false } };
}

const DAY_MS = 86_400_000;
const midnight = (day: string) => new Date(`${day}T00:00:00+03:00`).getTime();
const overlaps = (span: Span, day: string) =>
  new Date(span.start).getTime() < midnight(day) + DAY_MS &&
  new Date(span.end).getTime() > midnight(day);

function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** One listing's month: bookings and owner blocks, plus the block form (US3-AS3). */
export default async function OwnerCalendarPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user?.owner_profile) {
    redirect({
      href: user ? "/owner/onboarding" : "/account/sign-in?returnTo=/owner/calendar",
      locale,
    });
    return null;
  }

  const today = eatDateString(new Date());
  const month = query.month && /^\d{4}-\d{2}$/.test(query.month) ? query.month : today.slice(0, 7);
  const first = `${month}-01`;
  const last = addDays(`${shiftMonth(month, 1)}-01`, -1);
  const [t, calendar] = await Promise.all([getTranslations(), getOwnerCalendar(first, last)]);
  const listings = calendar?.listings ?? [];
  const selected = listings.find((l) => l.id === query.listing) ?? listings[0];
  const detail = selected ? await getOwnerListing(selected.id) : null;
  const isStock = detail?.category.booking_mode === "QUANTITY";
  const bookings = (calendar?.bookings ?? []).filter((b) => b.listing_id === selected?.id);
  const blocks = (calendar?.blocks ?? []).filter((b) => b.listing_id === selected?.id);

  const days = Array.from({ length: Number(last.slice(8)) }, (_, i) => addDays(first, i));
  const lead = (new Date(`${first}T12:00:00Z`).getUTCDay() + 6) % 7; // weeks start on Monday
  const href = (m: string) => `/owner/calendar?listing=${selected?.id ?? ""}&month=${m}`;
  const monthLabel = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "sw-TZ", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${first}T12:00:00Z`));
  const lastDay = (end: string) => new Date(new Date(end).getTime() - 1);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <OwnerNav current="calendar" />
      <h1 className="text-xl font-bold text-ink">{t("calendar.title")}</h1>
      {listings.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("calendar.noListings")}</p>
      ) : (
        <>
          <nav
            className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
            aria-label={t("calendar.listings")}
          >
            {listings.map((l) => (
              <Link
                key={l.id}
                href={`/owner/calendar?listing=${l.id}&month=${month}`}
                aria-current={l.id === selected?.id ? "page" : undefined}
                className={`max-w-48 shrink-0 truncate rounded-full px-3 py-1.5 text-sm ${
                  l.id === selected?.id
                    ? "bg-ink text-white"
                    : "bg-canvas text-ink hover:bg-brand-50"
                }`}
              >
                {l.title || t("ownerListings.untitled")}
              </Link>
            ))}
          </nav>

          <section className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-3">
            <div className="flex items-center justify-between">
              <Link
                href={href(shiftMonth(month, -1))}
                className="rounded-md px-2 py-1 text-brand-700 hover:bg-brand-50"
                aria-label={t("calendar.previous")}
              >
                ←
              </Link>
              <h2 className="text-base font-semibold capitalize text-ink">{monthLabel}</h2>
              <Link
                href={href(shiftMonth(month, 1))}
                className="rounded-md px-2 py-1 text-brand-700 hover:bg-brand-50"
                aria-label={t("calendar.next")}
              >
                →
              </Link>
            </div>
            <ol className="grid grid-cols-7 gap-1 text-center text-sm">
              {Array.from({ length: lead }, (_, i) => (
                <li key={`lead-${i}`} aria-hidden />
              ))}
              {days.map((day) => {
                const booked = bookings.some((b) => overlaps(b.period, day));
                const blocked = blocks.some((b) => overlaps(b.period, day));
                const state = booked ? "booked" : blocked ? "blocked" : "free";
                return (
                  <li
                    key={day}
                    title={`${formatDate(`${day}T12:00:00+03:00`, locale)}: ${t(`calendar.${state}`)}`}
                    className={`rounded-md py-2 ${
                      booked
                        ? "bg-brand-600 font-medium text-white"
                        : blocked
                          ? "bg-line text-muted line-through"
                          : "bg-canvas text-ink"
                    } ${day === today ? "ring-2 ring-brand-700" : ""}`}
                  >
                    {Number(day.slice(8))}
                  </li>
                );
              })}
            </ol>
            <p className="flex flex-wrap gap-3 text-xs text-muted">
              <span>
                <span className="mr-1 inline-block size-3 rounded-sm bg-brand-600 align-middle" />
                {t("calendar.booked")}
              </span>
              <span>
                <span className="mr-1 inline-block size-3 rounded-sm bg-line align-middle" />
                {t("calendar.blocked")}
              </span>
            </p>
          </section>

          {bookings.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="text-base font-semibold text-ink">{t("calendar.bookings")}</h2>
              <ul className="flex flex-col gap-2 text-sm">
                {bookings.map((b) => (
                  <li key={b.id}>
                    <Link
                      href={`/book/${b.id}`}
                      className="flex justify-between gap-2 rounded-lg border border-line p-3 hover:border-brand-600"
                    >
                      <span>
                        {b.code} · {b.renter_name}
                        {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
                      </span>
                      <span className="text-muted">{t(`bookingStatus.${b.status}`)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {selected && (
            <BlockForm
              listingId={selected.id}
              stock={isStock ? (detail?.stock ?? 1) : null}
              minDate={today}
            />
          )}
          {blocks.length > 0 && selected && (
            <section className="flex flex-col gap-2">
              <h2 className="text-base font-semibold text-ink">{t("calendar.blocks")}</h2>
              <ul className="flex flex-col gap-2 text-sm">
                {blocks.map((b) => (
                  <li
                    key={b.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-line p-3"
                  >
                    <span>
                      {formatDate(b.period.start, locale)} – {formatDate(lastDay(b.period.end), locale)}
                      {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
                      {b.note ? ` · ${b.note}` : ""}
                    </span>
                    <RemoveBlockButton listingId={selected.id} blockId={b.id} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
