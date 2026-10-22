import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { Pagination } from "@/components/Pagination";
import { ReportButton } from "@/components/ReportButton";
import { ReviewList } from "@/components/ReviewList";
import { Badge } from "@/components/ui/Badge";
import { getCurrentUser } from "@/lib/api/server";
import { getUserReviews } from "@/lib/api/social";

type Props = {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ page?: string }>;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE_SIZE = 10;

function stars(avg: number | null | undefined, count: number) {
  return count > 0 && avg != null ? `★ ${avg.toFixed(1)} (${count})` : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const data = UUID.test(id) ? await getUserReviews(id, 1) : null;
  if (!data) return {};
  return { title: data.profile.owner?.display_name ?? data.profile.name };
}

/** A public profile: ratings as owner and renter, and the reviews received (FR-029). */
export default async function ProfilePage({ params, searchParams }: Props) {
  const [{ locale: raw, id }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const page = Math.max(1, Number(query.page) || 1);
  const data = UUID.test(id) ? await getUserReviews(id, page) : null;
  if (!data) notFound();
  const [t, user] = await Promise.all([getTranslations(), getCurrentUser()]);
  const { profile } = data;
  const name = profile.owner?.display_name ?? profile.name;
  const ownerStars = profile.owner && stars(profile.owner.rating_avg, profile.owner.rating_count);
  const renterStars = stars(profile.renter_rating_avg, profile.renter_rating_count);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <header className="flex items-center gap-3">
        <div className="flex size-14 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xl font-semibold text-brand-800">
          {name.slice(0, 1).toUpperCase()}
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="truncate text-xl font-bold text-ink">{name}</h1>
          <div className="flex flex-wrap gap-2 text-sm text-muted">
            {profile.owner?.verified && <Badge tone="brand">{t("listing.verifiedOwner")}</Badge>}
            {ownerStars && <span>{t("reviews.asOwner", { stars: ownerStars })}</span>}
            {renterStars && <span>{t("reviews.asRenter", { stars: renterStars })}</span>}
          </div>
        </div>
      </header>

      <section className="flex flex-col gap-3 border-t border-line pt-4">
        <h2 className="text-base font-semibold text-ink">{t("listing.reviews")}</h2>
        {data.items.length === 0 ? (
          <p className="text-sm text-muted">{t("listing.noReviews")}</p>
        ) : (
          <ReviewList
            reviews={data.items}
            locale={locale}
            aboutLabel={(about) =>
              t(about === "owner" ? "reviews.aboutOwner" : "reviews.aboutRenter")
            }
          />
        )}
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          path={`/u/${id}`}
          pairs={[]}
        />
      </section>

      {user?.id !== profile.id && (
        <ReportButton
          targetKind="user"
          targetId={profile.id}
          signedIn={Boolean(user)}
          returnTo={`/u/${id}`}
        />
      )}
    </div>
  );
}
