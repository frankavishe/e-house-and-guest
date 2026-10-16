import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SignInForm } from "@/components/SignInForm";
import { redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { safeReturnTo } from "@/lib/returnTo";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ returnTo?: string }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "signIn" });
  return { title: t("title"), robots: { index: false } };
}

export default async function SignInPage({ params, searchParams }: Props) {
  const [{ locale }, { returnTo }] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const target = safeReturnTo(returnTo);

  const user = await getCurrentUser();
  if (user?.name) redirect({ href: target, locale });

  return <SignInForm returnTo={target} />;
}
