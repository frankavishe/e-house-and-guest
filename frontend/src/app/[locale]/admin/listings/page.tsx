import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdminActions } from "@/components/AdminActions";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { ListingStatusBadge } from "@/components/ListingStatusBadge";
import { getListingQueue } from "@/lib/api/owner";
import { formatTZS } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("listings"), robots: { index: false } };
}

const show = (value: unknown): string => {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.length ? String(value.length) : "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
};

/** Review queue: new listings and live listings with changes, each with the proposed diff. */
export default async function AdminListingsPage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [t, queue] = await Promise.all([getTranslations(), getListingQueue(1)]);
  const items = queue?.items ?? [];

  return (
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.listings")}</h1>
      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("admin.noListings")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map(({ listing, owner, diff }) => (
            <li key={listing.id} className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
              <div className="flex gap-3">
                <ImageWithFallback
                  src={listing.photos[0]?.url_320}
                  alt=""
                  fallbackLabel={t("common.imageUnavailable")}
                  className="size-20 shrink-0 rounded-lg"
                />
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="font-medium text-ink">{listing.title_sw || listing.title_en}</p>
                  <p className="text-sm text-muted">
                    {listing.category.name} · {owner.display_name} ({t(`owner.status.${owner.verification_status}`)})
                  </p>
                  {listing.base_price_tzs != null && (
                    <p className="text-sm">
                      {formatTZS(listing.base_price_tzs)} / {t(`units.${listing.category.default_unit}`)}
                    </p>
                  )}
                  <ListingStatusBadge listing={listing} />
                </div>
              </div>
              {diff ? (
                <table className="w-full text-left text-sm">
                  <thead className="text-muted">
                    <tr>
                      <th className="py-1 pr-2 font-medium">{t("admin.field")}</th>
                      <th className="py-1 pr-2 font-medium">{t("admin.before")}</th>
                      <th className="py-1 font-medium">{t("admin.after")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(diff).map(([field, change]) => (
                      <tr key={field} className="border-t border-line align-top">
                        <td className="py-1 pr-2 font-mono text-xs">{field}</td>
                        <td className="py-1 pr-2 break-all text-muted">{show(change.before)}</td>
                        <td className="py-1 break-all text-ink">{show(change.after)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <details className="text-sm">
                  <summary className="cursor-pointer text-brand-700">{t("admin.details")}</summary>
                  <p className="mt-2 whitespace-pre-line text-ink">
                    {listing.description_sw || listing.description_en}
                  </p>
                  <p className="mt-2 font-mono text-xs text-muted">{JSON.stringify(listing.attributes)}</p>
                </details>
              )}
              <AdminActions target={{ kind: "listing", id: listing.id, status: listing.status }} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
