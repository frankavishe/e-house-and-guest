import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { CategoryEditor } from "@/components/CategoryEditor";
import { Link } from "@/i18n/navigation";
import { getAdminCategories } from "@/lib/api/admin";
import { localized } from "@/lib/format";

type Props = { params: Promise<{ locale: string; id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("categories"), robots: { index: false } };
}

export default async function EditCategoryPage({ params }: Props) {
  const { locale: raw, id } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const [t, categories] = await Promise.all([getTranslations(), getAdminCategories()]);
  const category = categories?.find((c) => c.id === id);
  if (!category) notFound();

  return (
    <>
      <Link href="/admin/categories" className="text-sm text-brand-700 hover:underline">
        ← {t("admin.categories")}
      </Link>
      <h1 className="text-xl font-bold text-ink">{localized(category.name, locale)}</h1>
      <p className="text-sm text-muted">
        {category.path} · {t("adminCategories.version", { n: category.schema_version })}
      </p>
      <CategoryEditor
        key={category.id}
        locale={locale}
        category={category}
        groups={(categories ?? []).filter((c) => !c.is_leaf)}
      />
    </>
  );
}
