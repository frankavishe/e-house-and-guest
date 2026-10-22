import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import type { ListingCard as Card } from "@/lib/api/queries";
import { ImageWithFallback } from "./ImageWithFallback";
import { Money } from "./Money";
import { Badge } from "./ui/Badge";

/** One search result. `periodQuery` carries the searched dates to the listing page. */
export async function ListingCard({
  listing,
  periodQuery = "",
  priority = false,
}: {
  listing: Card;
  periodQuery?: string;
  priority?: boolean;
}) {
  const t = await getTranslations();
  const photo = listing.cover_photo;
  const base = listing.base_price;
  return (
    <article className="overflow-hidden rounded-xl border border-line bg-surface">
      <Link href={`/l/${listing.id}${periodQuery}`} className="flex h-full flex-col">
        <ImageWithFallback
          src={photo?.url_320}
          srcSet={photo ? `${photo.url_320} 320w, ${photo.url_640} 640w` : undefined}
          sizes="(min-width: 1024px) 320px, (min-width: 640px) calc(50vw - 24px), calc(100vw - 32px)"
          alt={photo?.alt ?? listing.title}
          fallbackLabel={t("common.imageUnavailable")}
          priority={priority}
        />
        <div className="flex flex-1 flex-col gap-1 p-3">
          <p className="text-xs text-muted">
            {listing.category.name} · {listing.location.district}, {listing.location.region}
          </p>
          <h3 className="line-clamp-2 text-base font-semibold leading-snug text-ink">
            {listing.title}
          </h3>
          {listing.highlights.length > 0 && (
            <p className="line-clamp-1 text-sm text-muted">
              {listing.highlights.map((h) => `${h.label}: ${h.value}`).join(" · ")}
            </p>
          )}
          <div className="mt-auto flex flex-wrap items-end justify-between gap-2 pt-2">
            <div>
              {listing.total_tzs != null ? (
                <>
                  <Money amount={listing.total_tzs} className="text-base font-bold text-ink" />
                  <span className="ml-1 text-xs text-muted">{t("search.totalForDates")}</span>
                </>
              ) : base ? (
                <span className="text-sm text-ink">
                  {t.rich("search.fromPrice", {
                    price: () => <Money amount={base.amount_tzs} className="font-bold" />,
                    unit: t(`units.${base.unit}`),
                  })}
                </span>
              ) : null}
              {listing.total_tzs != null && base && (
                <p className="text-xs text-muted">
                  <Money amount={base.amount_tzs} /> / {t(`units.${base.unit}`)}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1">
              {listing.rating_count > 0 && listing.rating_avg != null && (
                <span className="text-xs text-ink">
                  ★ {listing.rating_avg.toFixed(1)} ({listing.rating_count})
                </span>
              )}
              {listing.instant_book && <Badge tone="brand">{t("search.instantBook")}</Badge>}
            </div>
          </div>
        </div>
      </Link>
    </article>
  );
}
