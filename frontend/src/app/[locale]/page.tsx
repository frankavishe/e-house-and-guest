import { getTranslations, setRequestLocale } from "next-intl/server";

// Placeholder home; US1 (T059) replaces it with the category grid and search box.
export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");
  return (
    <section className="flex flex-col gap-3 py-8">
      <h1 className="text-2xl font-bold leading-tight text-ink sm:text-3xl">{t("title")}</h1>
      <p className="max-w-prose text-muted">{t("subtitle")}</p>
      <p className="text-sm text-muted">{t("comingSoon")}</p>
    </section>
  );
}
