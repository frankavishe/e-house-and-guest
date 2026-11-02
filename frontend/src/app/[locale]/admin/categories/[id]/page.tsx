import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { CategoryEditor } from "@/components/CategoryEditor";
import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <Link
        href="/admin/categories"
        className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
      >
        <Icon name="chevronLeft" className="size-4" />
        {t("admin.categories")}
      </Link>
      <PageHeader
        title={localized(category.name, locale)}
        subtitle={`${category.path} · ${t("adminCategories.version", { n: category.schema_version })}`}
      />
      <CategoryEditor
        key={category.id}
        locale={locale}
        category={category}
        groups={(categories ?? []).filter((c) => !c.is_leaf)}
      />
    </div>
  );
}
