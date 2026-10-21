import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { ListingStatusBadge } from "@/components/ListingStatusBadge";
import { OwnerNav } from "@/components/OwnerNav";
import { Pagination } from "@/components/Pagination";
import { buttonClasses } from "@/components/ui/Button";
import { Link, redirect } from "@/i18n/navigation";
import { getOwnerListings } from "@/lib/api/owner";
import { getCurrentUser } from "@/lib/api/server";
import { formatTZS } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ page?: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "ownerListings" });
  return { title: t("title"), robots: { index: false } };
}

export default async function OwnerListingsPage({ params, searchParams }: Props) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/owner/listings", locale });
    return null;
  }
  if (!user.owner_profile) {
    redirect({ href: "/owner/onboarding", locale });
    return null;
  }
  const page = Math.max(1, Number(query.page) || 1);
  const [t, result] = await Promise.all([getTranslations(), getOwnerListings(page)]);
  const items = result?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <OwnerNav current="listings" />
      <header className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-bold text-ink">{t("ownerListings.title")}</h1>
        <Link href="/owner/listings/new" className={buttonClasses("primary")}>
          {t("ownerListings.new")}
        </Link>
      </header>
      {user.owner_profile.verification_status !== "verified" && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
          {t("ownerListings.notVerified")}
        </p>
      )}

      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("ownerListings.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((l) => (
            <li key={l.id}>
              <Link
                href={`/owner/listings/${l.id}/edit`}
                className="flex gap-3 rounded-xl border border-line bg-surface p-3 hover:border-brand-600"
              >
                <ImageWithFallback
                  src={l.photos[0]?.url_320}
                  alt={l.title_sw ?? l.title_en ?? ""}
                  fallbackLabel={t("common.imageUnavailable")}
                  className="size-20 shrink-0 rounded-lg"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p className="truncate font-medium text-ink">
                    {(locale === "en" ? l.title_en || l.title_sw : l.title_sw || l.title_en) ||
                      t("ownerListings.untitled")}
                  </p>
                  <p className="text-sm text-muted">
                    {l.category.name}
                    {l.base_price_tzs != null &&
                      ` · ${formatTZS(l.base_price_tzs)} / ${t(`units.${l.category.default_unit}`)}`}
                  </p>
                  <ListingStatusBadge listing={l} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {result && (
        <Pagination
          pairs={[]}
          page={page}
          pageSize={result.page_size}
          total={result.total}
          path="/owner/listings"
        />
      )}
    </div>
  );
}
