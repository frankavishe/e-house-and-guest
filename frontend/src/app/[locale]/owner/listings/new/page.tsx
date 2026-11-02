import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { NewListingForm } from "@/components/NewListingForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirect } from "@/i18n/navigation";
import { getCategories, type CategoryNode } from "@/lib/api/queries";
import { getCurrentUser } from "@/lib/api/server";
import { localized } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "ownerListings" });
  return { title: t("new"), robots: { index: false } };
}

/** Leaf categories labelled "Group › Leaf", in tree order. */
function leaves(
  nodes: CategoryNode[],
  locale: "sw" | "en",
  prefix = "",
): { value: string; label: string }[] {
  return nodes.flatMap((node) => {
    const name = localized(node.name, locale);
    const label = prefix ? `${prefix} › ${name}` : name;
    return node.booking_mode
      ? [{ value: node.id, label }]
      : leaves(node.children ?? [], locale, label);
  });
}

export default async function NewListingPage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user?.owner_profile) {
    redirect({
      href: user ? "/owner/onboarding" : "/account/sign-in?returnTo=/owner/listings/new",
      locale,
    });
    return null;
  }
  const [t, categories] = await Promise.all([getTranslations("ownerListings"), getCategories()]);
  return (
    <div className="flex w-full max-w-3xl flex-col gap-5">
      <PageHeader title={t("new")} subtitle={t("newHint")} />
      <NewListingForm categories={leaves(categories, locale === "en" ? "en" : "sw")} />
    </div>
  );
}
