import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { OwnerOnboarding } from "@/components/OwnerOnboarding";
import { redirect } from "@/i18n/navigation";
import { getOwnerProfile } from "@/lib/api/owner";
import { getCurrentUser } from "@/lib/api/server";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "owner" });
  return { title: t("title"), robots: { index: false } };
}

export default async function OwnerOnboardingPage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/owner/onboarding", locale });
    return null;
  }
  const [t, profile] = await Promise.all([
    getTranslations("owner"),
    user.owner_profile ? getOwnerProfile() : null,
  ]);

  return (
    <div className="flex w-full max-w-3xl flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("title")}</h1>
        <p className="text-sm text-muted">{t("intro")}</p>
      </header>
      <OwnerOnboarding profile={profile} />
    </div>
  );
}
