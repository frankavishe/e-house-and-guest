import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { ListingWizard } from "@/components/ListingWizard";
import { redirect } from "@/i18n/navigation";
import { getOwnerListing } from "@/lib/api/owner";
import { getCategory, getLocations } from "@/lib/api/queries";
import { getCurrentUser } from "@/lib/api/server";
import { isStep, type Step } from "@/lib/wizard";

type Props = {
  params: Promise<{ locale: string; id: string }>;
  searchParams: Promise<{ step?: string }>;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TILE_URL =
  process.env.NEXT_PUBLIC_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "wizard" });
  return { title: t("title"), robots: { index: false } };
}

export default async function EditListingPage({ params, searchParams }: Props) {
  const [{ locale, id }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: `/account/sign-in?returnTo=/owner/listings/${id}/edit`, locale });
    return null;
  }
  const listing = UUID.test(id) ? await getOwnerListing(id) : null;
  if (!listing) notFound();

  const regionId = listing.pending_changes?.region_id ?? listing.region_id;
  const [category, regions, districts] = await Promise.all([
    getCategory(listing.category.slug),
    getLocations(),
    regionId ? getLocations(Number(regionId)) : Promise.resolve([]),
  ]);
  const step: Step = isStep(query.step)
    ? query.step
    : listing.status === "draft" && listing.missing.length === 0
      ? "review"
      : "details";
  const option = (l: { id: number; name: string }) => ({ value: String(l.id), label: l.name });

  return (
    <div className="w-full max-w-3xl">
      <ListingWizard
        initial={listing}
        schema={(category?.attribute_schema ?? []) as Record<string, unknown>[]}
        regions={regions.map(option)}
        districts={districts.map(option)}
        step={step}
        tileUrl={TILE_URL}
      />
    </div>
  );
}
