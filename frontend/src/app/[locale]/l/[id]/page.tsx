import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { BookingWidget } from "@/components/BookingWidget";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { addDays, ListingAvailability } from "@/components/ListingAvailability";
import { MessageOwnerButton } from "@/components/MessageOwnerButton";
import { Money } from "@/components/Money";
import { ReportButton } from "@/components/ReportButton";
import { ReviewList } from "@/components/ReviewList";
import { ShareLinks } from "@/components/ShareLinks";
import { Icon } from "@/components/icons";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Link } from "@/i18n/navigation";
import { getAvailability, getListing, type ListingDetail } from "@/lib/api/queries";
import { getCurrentUser } from "@/lib/api/server";
import { eatDateString, formatDate, formatTZS } from "@/lib/format";
import { cleanParams, getParam, type RawParams } from "@/lib/search";

type Props = {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<RawParams>;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const WINDOW_DAYS: Record<ListingDetail["booking_mode"], number> = {
  DATE_RANGE: 60,
  LEASE: 60,
  TIME_SLOT: 7,
  QUANTITY: 14,
};

async function load(id: string) {
  return UUID.test(id) ? getListing(id) : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const listing = await load(id);
  if (!listing) return {};
  const description = listing.description.slice(0, 160);
  const image = listing.photos[0]?.url_640;
  return {
    title: listing.title,
    description,
    openGraph: {
      title: listing.title,
      description,
      type: "website",
      images: image ? [{ url: image, width: 640, alt: listing.photos[0].alt }] : undefined,
    },
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

export default async function ListingPage({ params, searchParams }: Props) {
  const [{ locale: raw, id }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const listing = await load(id);
  if (!listing) notFound();

  const today = eatDateString(new Date());
  const pairs = cleanParams(query);
  const asked = getParam(pairs, "start_date") ?? getParam(pairs, "slot_date");
  const from = asked && /^\d{4}-\d{2}-\d{2}$/.test(asked) && asked > today ? asked : today;
  const days = WINDOW_DAYS[listing.booking_mode];
  const [t, availability, head, user] = await Promise.all([
    getTranslations(),
    getAvailability(listing.id, from, addDays(from, days - 1)),
    headers(),
    getCurrentUser(),
  ]);
  const host = head.get("x-forwarded-host") ?? head.get("host") ?? "localhost";
  const proto = head.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const shareUrl = `${proto}://${host}/${locale}/l/${listing.id}`;
  const isOwner = user?.id === listing.owner.user_id;

  const groups = new Map<string, typeof listing.attributes>();
  for (const attr of listing.attributes) {
    const key = attr.group ?? "";
    groups.set(key, [...(groups.get(key) ?? []), attr]);
  }
  const basePrices = listing.prices.filter((p) => !p.season_start);
  const seasonal = listing.prices.filter((p) => p.season_start);
  const unit = (u: string) => t(`units.${u}`);

  const booking = (
    <BookingWidget listing={listing} signedIn={Boolean(user)} initial={Object.fromEntries(pairs)} />
  );

  const priceCard = listing.base_price && (
    <div className="relative overflow-hidden rounded-[var(--radius-card)] bg-hero p-5 text-white">
      <span
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 size-36 rounded-full border-[18px] border-white/10"
      />
      <p className="text-sm text-white/80">{t("listing.prices")}</p>
      <p className="mt-1 text-3xl font-semibold tracking-tight">
        <Money amount={listing.base_price.amount_tzs} />
        <span className="ml-1 text-base font-normal text-white/80">
          / {unit(listing.base_price.unit)}
        </span>
      </p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {listing.instant_book && (
          <span className="rounded-full bg-white/20 px-2.5 py-1 font-medium">
            {t("search.instantBook")}
          </span>
        )}
        <span className="rounded-full bg-white/20 px-2.5 py-1 font-medium">
          {t(`policy.${listing.cancellation_policy}`)}
        </span>
      </div>
    </div>
  );

  const ownerCard = (
    <div className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5">
      <p className="text-sm font-medium text-muted">
        {listing.owner.verified ? t("listing.verifiedOwner") : t("listing.owner")}
      </p>
      <Link href={`/u/${listing.owner.user_id}`} className="group flex items-center gap-3">
        <Avatar name={listing.owner.display_name} />
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink group-hover:text-brand-700">
            {listing.owner.display_name}
          </p>
          {listing.owner.rating_count > 0 && listing.owner.rating_avg != null && (
            <p className="flex items-center gap-1 text-xs text-muted">
              <Icon name="star" className="size-3.5 fill-accent-500 stroke-accent-500" />
              {listing.owner.rating_avg.toFixed(1)} ({listing.owner.rating_count})
            </p>
          )}
        </div>
        {listing.owner.verified && (
          <span className="ml-auto flex size-10 items-center justify-center rounded-full bg-brand-600 text-white">
            <Icon name="shield" />
          </span>
        )}
      </Link>
      {!isOwner && <MessageOwnerButton listingId={listing.id} signedIn={Boolean(user)} />}
    </div>
  );

  return (
    <article className="flex flex-col gap-5">
      <nav className="text-sm">
        <Link
          href={`/search?category=${listing.category.slug}`}
          className="inline-flex items-center gap-1 rounded-full bg-card px-3 py-1.5 font-medium text-ink hover:bg-brand-50 hover:text-brand-700"
        >
          <Icon name="chevronLeft" className="size-4" />
          {listing.category.name}
        </Link>
      </nav>

      <div
        className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 [scrollbar-width:thin] sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0"
        aria-label={t("listing.photos")}
      >
        {(listing.photos.length ? listing.photos : [null]).map((photo, i) => (
          <ImageWithFallback
            key={photo?.url_640 ?? i}
            src={photo?.url_640}
            srcSet={
              photo
                ? `${photo.url_320} 320w, ${photo.url_640} 640w, ${photo.url_1280} 1280w`
                : undefined
            }
            sizes="(min-width: 640px) 600px, 90vw"
            alt={photo?.alt ?? listing.title}
            fallbackLabel={t("common.imageUnavailable")}
            priority={i === 0}
            className="w-[90%] shrink-0 snap-center rounded-[var(--radius-card)] sm:w-[600px]"
          />
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_380px] lg:grid-rows-[auto_1fr] lg:gap-x-6">
        <header className="flex min-w-0 flex-col gap-2 lg:col-start-1 lg:row-start-1">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight text-ink">
            {listing.title}
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="inline-flex items-center gap-1">
              <Icon name="pin" className="size-4" />
              {listing.location.district}, {listing.location.region}
            </span>
            {listing.rating_count > 0 && listing.rating_avg != null && (
              <span className="inline-flex items-center gap-1 text-ink">
                <Icon name="star" className="size-4 fill-accent-500 stroke-accent-500" />
                {listing.rating_avg.toFixed(1)}
                <span className="text-muted">({listing.rating_count})</span>
              </span>
            )}
            {listing.instant_book && <Badge tone="brand">{t("search.instantBook")}</Badge>}
          </div>
        </header>

        <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start">
          {priceCard}
          {booking}
          {ownerCard}
        </aside>

        <div className="flex min-w-0 flex-col gap-5 lg:col-start-1 lg:row-start-2">
          <p className="whitespace-pre-line leading-relaxed text-ink">{listing.description}</p>

          {listing.attributes.length > 0 && (
            <Section title={t("listing.details")}>
              {[...groups.entries()].map(([group, attrs]) => (
                <div key={group || "_"} className="flex flex-col gap-1">
                  {group && <h3 className="text-sm font-medium text-muted">{group}</h3>}
                  <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {attrs.map((a) => (
                      <div
                        key={a.key}
                        className="flex flex-col-reverse gap-0.5 rounded-2xl bg-surface p-3"
                      >
                        <dt className="text-xs text-muted">{a.label}</dt>
                        <dd className="font-semibold text-ink">
                          {a.display}
                          {a.unit ? ` ${a.unit}` : ""}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </Section>
          )}

          <Section title={t("listing.prices")}>
            <ul className="flex flex-col gap-1 text-sm">
              {basePrices.map((p) => (
                <li key={p.unit} className="flex justify-between">
                  <span className="text-muted">{t("listing.perUnit", { unit: unit(p.unit) })}</span>
                  <Money amount={p.amount_tzs} className="font-medium" />
                </li>
              ))}
              {seasonal.map((p) => (
                <li key={`${p.unit}-${p.season_start}`} className="flex justify-between">
                  <span className="text-muted">
                    {t("listing.season", {
                      from: formatDate(`${p.season_start}T12:00:00+03:00`, locale),
                      to: formatDate(`${p.season_end}T12:00:00+03:00`, locale),
                      unit: unit(p.unit),
                    })}
                  </span>
                  <Money amount={p.amount_tzs} className="font-medium" />
                </li>
              ))}
            </ul>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">{t("listing.deposit")}</dt>
              <dd>
                {listing.deposit_tzs ? (
                  <Money amount={listing.deposit_tzs} />
                ) : (
                  t("listing.noDeposit")
                )}
              </dd>
              <dt className="text-muted">{t("listing.delivery")}</dt>
              <dd>
                {listing.delivery === "none"
                  ? t("listing.deliveryNone")
                  : t(`listing.delivery_${listing.delivery}`, {
                      fee: listing.delivery_fee_tzs
                        ? formatTZS(listing.delivery_fee_tzs)
                        : t("listing.deliveryFree"),
                    })}
              </dd>
              {(listing.min_duration != null || listing.max_duration != null) && (
                <>
                  <dt className="text-muted">{t("listing.duration")}</dt>
                  <dd>
                    {[
                      listing.min_duration != null &&
                        t("listing.minDuration", {
                          count: listing.min_duration,
                          unit: unit(listing.default_unit),
                        }),
                      listing.max_duration != null &&
                        t("listing.maxDuration", {
                          count: listing.max_duration,
                          unit: unit(listing.default_unit),
                        }),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </dd>
                </>
              )}
              {listing.booking_mode === "QUANTITY" && (
                <>
                  <dt className="text-muted">{t("listing.stock")}</dt>
                  <dd>{listing.stock}</dd>
                </>
              )}
              <dt className="text-muted">{t("listing.cancellation")}</dt>
              <dd>{t(`policy.${listing.cancellation_policy}`)}</dd>
            </dl>
          </Section>

          <Section title={t("listing.availability")}>
            <ListingAvailability
              availability={availability}
              from={from}
              days={days}
              locale={locale}
            />
          </Section>

          <Section title={t("listing.reviews")}>
            {listing.reviews.length === 0 ? (
              <p className="text-sm text-muted">{t("listing.noReviews")}</p>
            ) : (
              <ReviewList reviews={listing.reviews} locale={locale} />
            )}
            {listing.rating_count > listing.reviews.length && (
              <Link
                href={`/u/${listing.owner.user_id}`}
                className="text-sm text-brand-700 hover:underline"
              >
                {t("reviews.allOwnerReviews", { count: listing.owner.rating_count })}
              </Link>
            )}
          </Section>

          <Section title={t("listing.share")}>
            <ShareLinks
              url={shareUrl}
              title={listing.title}
              labels={{
                whatsapp: t("listing.shareWhatsapp"),
                share: t("listing.shareLink"),
                copied: t("listing.copied"),
              }}
            />
          </Section>

          {!isOwner && (
            <ReportButton
              targetKind="listing"
              targetId={listing.id}
              signedIn={Boolean(user)}
              returnTo={`/l/${listing.id}`}
            />
          )}
        </div>
      </div>
    </article>
  );
}
