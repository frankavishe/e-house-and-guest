import { getTranslations, setRequestLocale } from "next-intl/server";
import { PeriodFields } from "@/components/PeriodFields";
import { CleanGetForm } from "@/components/SearchControls";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Link } from "@/i18n/navigation";
import { flattenCategories, getCategories, getLocations } from "@/lib/api/queries";
import { localized } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

export default async function HomePage({ params }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const [t, categories, regions] = await Promise.all([
    getTranslations(),
    getCategories(),
    getLocations(),
  ]);
  const name = (node: { name: { sw: string; en: string } }) => localized(node.name, locale);

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3 pt-2">
        <h1 className="text-2xl font-bold leading-tight text-ink sm:text-3xl">{t("home.title")}</h1>
        <p className="max-w-prose text-muted">{t("home.subtitle")}</p>
      </section>

      <CleanGetForm
        action={`/${locale}/search`}
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-sm"
      >
        <h2 className="sr-only">{t("home.searchTitle")}</h2>
        <Input
          label={t("home.whatLabel")}
          name="q"
          type="search"
          placeholder={t("home.whatPlaceholder")}
          maxLength={100}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label={t("filters.category")}
            name="category"
            placeholder={t("filters.allCategories")}
            options={flattenCategories(categories, name)}
          />
          <Select
            label={t("filters.region")}
            name="region"
            placeholder={t("filters.allRegions")}
            options={regions.map((r) => ({ value: String(r.id), label: r.name }))}
          />
        </div>
        <PeriodFields mode={null} pairs={[]} />
        <Button type="submit" size="lg" full>
          {t("home.search")}
        </Button>
      </CleanGetForm>

      <section aria-labelledby="browse" className="flex flex-col gap-3">
        <h2 id="browse" className="text-lg font-semibold text-ink">
          {t("home.browse")}
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((group) => (
            <li key={group.id} className="rounded-xl border border-line bg-surface p-4">
              <Link
                href={`/search?category=${group.slug}`}
                className="text-base font-semibold text-brand-800 hover:underline"
              >
                {name(group)}
              </Link>
              {(group.children ?? []).length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-2">
                  {(group.children ?? []).map((leaf) => (
                    <li key={leaf.id}>
                      <Link
                        href={`/search?category=${leaf.slug}`}
                        className="inline-flex min-h-9 items-center rounded-full border border-line px-3 text-sm text-ink hover:border-brand-600 hover:bg-brand-50"
                      >
                        {name(leaf)}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
