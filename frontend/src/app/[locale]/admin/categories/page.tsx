import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Badge } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";
import { getAdminCategories } from "@/lib/api/admin";
import { localized } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("categories"), robots: { index: false } };
}

/** The category tree, inactive categories included. Leaves hold listings; a new leaf is
 * listable and filterable as soon as it is saved (US7-AS1). */
export default async function AdminCategoriesPage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const [t, categories] = await Promise.all([getTranslations(), getAdminCategories()]);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("admin.categories")}</h1>
        <Link href="/admin/categories/new" className={buttonClasses()}>
          {t("adminCategories.new")}
        </Link>
      </div>
      <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-3xl bg-card">
        {(categories ?? []).map((c) => {
          const depth = c.path.split(".").length - 1;
          return (
            <li key={c.id} className="flex flex-wrap items-center gap-2 px-4 py-3">
              <span style={{ paddingInlineStart: `${depth * 1.25}rem` }} className="min-w-0 flex-1">
                <Link
                  href={`/admin/categories/${c.id}`}
                  className="font-medium text-brand-700 hover:underline"
                >
                  {localized(c.name, locale)}
                </Link>
                <span className="ml-2 text-xs text-muted">{c.slug}</span>
              </span>
              {c.is_leaf ? (
                <span className="text-sm text-muted">
                  {t("adminCategories.listingCount", { count: c.listing_count })} ·{" "}
                  {t("adminCategories.fieldCount", { count: c.attribute_schema.length })}
                </span>
              ) : (
                <Badge>{t("adminCategories.group")}</Badge>
              )}
              {!c.is_active && <Badge tone="warning">{t("adminCategories.inactive")}</Badge>}
            </li>
          );
        })}
      </ul>
    </>
  );
}
