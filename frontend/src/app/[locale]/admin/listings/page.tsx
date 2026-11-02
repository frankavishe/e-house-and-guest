import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdminActions } from "@/components/AdminActions";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { ListingStatusBadge } from "@/components/ListingStatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.listings")} subtitle={t("admin.sub_listings")} />
      {items.length === 0 ? (
        <EmptyState icon="checkCircle">{t("admin.noListings")}</EmptyState>
      ) : (
        <ul className="flex flex-col gap-4">
          {items.map(({ listing, owner, diff }) => (
            <li
              key={listing.id}
              className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5"
            >
              <div className="flex gap-4">
                <ImageWithFallback
                  src={listing.photos[0]?.url_320}
                  alt=""
                  fallbackLabel={t("common.imageUnavailable")}
                  className="size-24 shrink-0 rounded-2xl"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="font-semibold text-ink">{listing.title_sw || listing.title_en}</p>
                    <ListingStatusBadge listing={listing} />
                  </div>
                  <p className="text-sm text-muted">
                    {listing.category.name} · {owner.display_name} (
                    {t(`owner.status.${owner.verification_status}`)})
                  </p>
                  {listing.base_price_tzs != null && (
                    <p className="text-sm font-semibold text-ink">
                      {formatTZS(listing.base_price_tzs)}{" "}
                      <span className="font-normal text-muted">
                        / {t(`units.${listing.category.default_unit}`)}
                      </span>
                    </p>
                  )}
                </div>
              </div>
              {diff ? (
                <div className="-mx-5 overflow-x-auto px-5">
                  <table className="w-full min-w-[32rem] text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th className="pb-2 pr-3 font-medium">{t("admin.field")}</th>
                        <th className="pb-2 pr-3 font-medium">{t("admin.before")}</th>
                        <th className="pb-2 font-medium">{t("admin.after")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(diff).map(([field, change]) => (
                        <tr key={field} className="border-t border-line align-top">
                          <td className="py-2 pr-3 font-mono text-xs">{field}</td>
                          <td className="py-2 pr-3 break-all text-muted">{show(change.before)}</td>
                          <td className="py-2 break-all">
                            <span className="rounded-md bg-success-soft px-1.5 py-0.5 text-success">
                              {show(change.after)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <details className="rounded-2xl bg-surface p-3 text-sm">
                  <summary className="cursor-pointer font-medium text-brand-700">
                    {t("admin.details")}
                  </summary>
                  <p className="mt-2 whitespace-pre-line text-ink">
                    {listing.description_sw || listing.description_en}
                  </p>
                  <p className="mt-2 break-all font-mono text-xs text-muted">
                    {JSON.stringify(listing.attributes)}
                  </p>
                </details>
              )}
              <AdminActions target={{ kind: "listing", id: listing.id, status: listing.status }} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
