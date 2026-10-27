import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
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

  const all = categories ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title={t("admin.categories")}
        subtitle={t("admin.sub_categories")}
        actions={
          <Link href="/admin/categories/new" className={buttonClasses("primary", "md")}>
            <Icon name="plus" className="size-4" />
            {t("adminCategories.new")}
          </Link>
        }
      />
      {all.length === 0 ? (
        <EmptyState icon="tag">{t("errors.generic")}</EmptyState>
      ) : (
        <ul className="flex flex-col gap-1 rounded-[var(--radius-card)] bg-card p-3">
          {all.map((c) => {
            const depth = c.path.split(".").length - 1;
            return (
              <li key={c.id}>
                <Link
                  href={`/admin/categories/${c.id}`}
                  style={{ paddingInlineStart: `${0.75 + depth * 1.5}rem` }}
                  className={`flex flex-wrap items-center gap-3 rounded-2xl py-2.5 pr-3 hover:bg-surface ${
                    c.is_active ? "" : "opacity-70"
                  }`}
                >
                  <span
                    className={`flex size-9 shrink-0 items-center justify-center rounded-full ${
                      c.is_leaf ? "bg-brand-100 text-brand-700" : "bg-ink text-surface"
                    }`}
                  >
                    <Icon name={c.is_leaf ? "tag" : "grid"} className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-ink">
                      {localized(c.name, locale)}
                    </span>
                    <span className="block truncate text-xs text-muted">{c.slug}</span>
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
                  <Icon name="chevronRight" className="size-4 text-muted" />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
