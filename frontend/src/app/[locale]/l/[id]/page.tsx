import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { addDays, ListingAvailability } from "@/components/ListingAvailability";
import { Money } from "@/components/Money";
import { ShareLinks } from "@/components/ShareLinks";
import { Badge } from "@/components/ui/Badge";
import { Link } from "@/i18n/navigation";
import { getAvailability, getListing, type ListingDetail } from "@/lib/api/queries";
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
    <section className="flex flex-col gap-2 border-t border-line pt-4">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
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
  const asked =
    getParam(cleanParams(query), "start_date") ?? getParam(cleanParams(query), "slot_date");
  const from = asked && /^\d{4}-\d{2}-\d{2}$/.test(asked) && asked > today ? asked : today;
  const days = WINDOW_DAYS[listing.booking_mode];
  const [t, availability, head] = await Promise.all([
    getTranslations(),
    getAvailability(listing.id, from, addDays(from, days - 1)),
    headers(),
  ]);
  const host = head.get("x-forwarded-host") ?? head.get("host") ?? "localhost";
  const proto = head.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const shareUrl = `${proto}://${host}/${locale}/l/${listing.id}`;

  const groups = new Map<string, typeof listing.attributes>();
  for (const attr of listing.attributes) {
    const key = attr.group ?? "";
    groups.set(key, [...(groups.get(key) ?? []), attr]);
  }
  const basePrices = listing.prices.filter((p) => !p.season_start);
  const seasonal = listing.prices.filter((p) => p.season_start);
  const unit = (u: string) => t(`units.${u}`);

  return (
    <article className="flex flex-col gap-5">
      <nav className="text-sm">
        <Link
          href={`/search?category=${listing.category.slug}`}
          className="text-brand-700 hover:underline"
        >
          ← {listing.category.name}
        </Link>
      </nav>

      <div
        className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 sm:mx-0 sm:px-0"
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
            className="w-[90%] shrink-0 snap-center rounded-xl sm:w-[600px]"
          />
        ))}
      </div>

      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold leading-tight text-ink">{listing.title}</h1>
        <p className="text-sm text-muted">
          {listing.location.district}, {listing.location.region}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {listing.instant_book && <Badge tone="brand">{t("search.instantBook")}</Badge>}
          {listing.rating_count > 0 && listing.rating_avg != null && (
            <span className="text-sm">
              ★ {listing.rating_avg.toFixed(1)} ({listing.rating_count})
            </span>
          )}
        </div>
        {listing.base_price && (
          <p className="text-lg text-ink">
            <Money amount={listing.base_price.amount_tzs} className="font-bold" />{" "}
            <span className="text-sm text-muted">/ {unit(listing.base_price.unit)}</span>
          </p>
        )}
      </header>

      <div className="flex items-center gap-3 rounded-xl border border-line bg-surface p-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-50 font-semibold text-brand-800">
          {listing.owner.display_name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{listing.owner.display_name}</p>
          <p className="text-xs text-muted">
            {listing.owner.verified ? t("listing.verifiedOwner") : t("listing.owner")}
            {listing.owner.rating_count > 0 && listing.owner.rating_avg != null
              ? ` · ★ ${listing.owner.rating_avg.toFixed(1)}`
              : ""}
          </p>
        </div>
      </div>

      <p className="whitespace-pre-line text-ink">{listing.description}</p>

      {listing.attributes.length > 0 && (
        <Section title={t("listing.details")}>
          {[...groups.entries()].map(([group, attrs]) => (
            <div key={group || "_"} className="flex flex-col gap-1">
              {group && <h3 className="text-sm font-medium text-muted">{group}</h3>}
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {attrs.map((a) => (
                  <div key={a.key} className="contents">
                    <dt className="text-muted">{a.label}</dt>
                    <dd className="text-ink">
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
            {listing.deposit_tzs ? <Money amount={listing.deposit_tzs} /> : t("listing.noDeposit")}
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
        <ListingAvailability availability={availability} from={from} days={days} locale={locale} />
      </Section>

      <Section title={t("listing.reviews")}>
        {listing.reviews.length === 0 ? (
          <p className="text-sm text-muted">{t("listing.noReviews")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {listing.reviews.map((r) => (
              <li key={`${r.author}-${r.created_at}`} className="text-sm">
                <p className="font-medium">
                  {"★".repeat(r.rating)} · {r.author}
                </p>
                {r.comment && <p className="text-ink">{r.comment}</p>}
              </li>
            ))}
          </ul>
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
    </article>
  );
}
