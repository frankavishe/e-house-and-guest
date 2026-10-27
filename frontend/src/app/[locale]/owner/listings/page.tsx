import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Icon } from "@/components/icons";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { ListingStatusBadge } from "@/components/ListingStatusBadge";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("ownerListings.title")} />
      {user.owner_profile.verification_status !== "verified" && (
        <p className="rounded-2xl bg-warning-soft p-3 text-sm text-warning">
          {t("ownerListings.notVerified")}
        </p>
      )}

      {items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed border-line p-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-brand-100 text-brand-700">
            <Icon name="grid" />
          </span>
          <p className="text-muted">{t("ownerListings.empty")}</p>
          <Link href="/owner/listings/new" className={buttonClasses("primary")}>
            <Icon name="plus" className="size-4" />
            {t("ownerListings.new")}
          </Link>
        </div>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((l) => (
            <li key={l.id}>
              <Link
                href={`/owner/listings/${l.id}/edit`}
                className="group flex h-full flex-col rounded-[var(--radius-card)] bg-card p-2 transition-shadow hover:shadow-soft"
              >
                <div className="relative">
                  <ImageWithFallback
                    src={l.photos[0]?.url_320}
                    alt={l.title_sw ?? l.title_en ?? ""}
                    fallbackLabel={t("common.imageUnavailable")}
                    className="rounded-[1.1rem]"
                  />
                  <span className="absolute left-2 top-2 rounded-full bg-surface/95 p-0.5">
                    <ListingStatusBadge listing={l} />
                  </span>
                </div>
                <div className="flex flex-1 flex-col gap-1 px-2.5 pb-2 pt-3">
                  <p className="truncate font-semibold text-ink group-hover:text-brand-700">
                    {(locale === "en" ? l.title_en || l.title_sw : l.title_sw || l.title_en) ||
                      t("ownerListings.untitled")}
                  </p>
                  <p className="text-sm text-muted">{l.category.name}</p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    {l.base_price_tzs != null ? (
                      <p className="text-sm">
                        <span className="font-semibold text-ink">
                          {formatTZS(l.base_price_tzs)}
                        </span>
                        <span className="text-muted">
                          {" "}
                          / {t(`units.${l.category.default_unit}`)}
                        </span>
                      </p>
                    ) : (
                      <span />
                    )}
                    <span className="flex size-8 items-center justify-center rounded-full bg-surface text-muted group-hover:bg-brand-600 group-hover:text-white">
                      <Icon name="edit" className="size-4" />
                    </span>
                  </div>
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
