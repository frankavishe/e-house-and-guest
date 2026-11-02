import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { CategoryEditor } from "@/components/CategoryEditor";
import { Icon } from "@/components/icons";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <Link
        href="/admin/categories"
        className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
      >
        <Icon name="chevronLeft" className="size-4" />
        {t("admin.categories")}
      </Link>
      <PageHeader title={t("adminCategories.new")} />
      <CategoryEditor locale={locale} groups={(categories ?? []).filter((c) => !c.is_leaf)} />
    </div>
  );
}
