import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { CategoryEditor } from "@/components/CategoryEditor";
import { Link } from "@/i18n/navigation";
import { getAdminCategories } from "@/lib/api/admin";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "adminCategories" });
  return { title: t("new"), robots: { index: false } };
}

export default async function NewCategoryPage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const [t, categories] = await Promise.all([getTranslations(), getAdminCategories()]);

  return (
    <>
      <Link href="/admin/categories" className="text-sm text-brand-700 hover:underline">
        ← {t("admin.categories")}
      </Link>
      <h1 className="text-xl font-bold text-ink">{t("adminCategories.new")}</h1>
      <CategoryEditor locale={locale} groups={(categories ?? []).filter((c) => !c.is_leaf)} />
    </>
  );
}
