import { getTranslations, setRequestLocale } from "next-intl/server";
import { Icon, type IconName } from "@/components/icons";
import { PeriodFields } from "@/components/PeriodFields";
import { CleanGetForm } from "@/components/SearchControls";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Link } from "@/i18n/navigation";
import { flattenCategories, getCategories, getLocations } from "@/lib/api/queries";
import { localized } from "@/lib/format";

type Props = { params: Promise<{ locale: string }> };

const NETWORKS = ["M-Pesa", "Mixx", "Airtel Money", "HaloPesa"];

/** Icon chip per top-level category; unknown slugs get the grid icon. */
const CATEGORY_ICONS: Record<string, IconName> = {
  accommodation: "home",
  workspace: "building",
  venues: "users",
  "storage-property": "box",
  vehicles: "car",
  equipment: "wrench",
};

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
  const steps: [IconName, string, string][] = [
    ["search", t("homeExtra.step1"), t("homeExtra.step1Hint")],
    ["smartphone", t("homeExtra.step2"), t("homeExtra.step2Hint")],
    ["sparkles", t("homeExtra.step3"), t("homeExtra.step3Hint")],
  ];

  return (
    <div className="flex flex-col gap-10">
      <div className="grid gap-4 lg:grid-cols-[1.05fr_1fr]">
        <section className="relative flex flex-col justify-between gap-8 overflow-hidden rounded-[var(--radius-card)] bg-hero p-6 text-white sm:p-8">
          <span
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-16 size-64 rounded-full border-[28px] border-white/10"
          />
          <span
            aria-hidden
            className="pointer-events-none absolute -bottom-24 right-24 size-48 rounded-full bg-white/10"
          />
          <div className="relative flex flex-col gap-4">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium backdrop-blur">
              <Icon name="shield" className="size-3.5" />
              {t("homeExtra.badge")}
            </span>
            <h1 className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
              {t("home.title")}
            </h1>
            <p className="max-w-prose text-white/85">{t("home.subtitle")}</p>
          </div>
          <ul className="relative flex flex-wrap gap-2" aria-label={t("footer.pay")}>
            {NETWORKS.map((n) => (
              <li
                key={n}
                className="rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-brand-700"
              >
                {n}
              </li>
            ))}
          </ul>
        </section>

        <CleanGetForm
          action={`/${locale}/search`}
          className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5 sm:p-6"
        >
          <h2 className="text-lg font-semibold">{t("home.searchTitle")}</h2>
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
          <Button type="submit" size="lg" full className="mt-1">
            <Icon name="search" className="size-4" />
            {t("home.search")}
          </Button>
        </CleanGetForm>
      </div>

      <section aria-labelledby="browse" className="flex flex-col gap-4">
        <h2 id="browse" className="text-xl font-semibold tracking-tight">
          {t("home.browse")}
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((group) => (
            <li
              key={group.id}
              className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5"
            >
              <Link
                href={`/search?category=${group.slug}`}
                className="group flex items-center gap-3"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
                  <Icon name={CATEGORY_ICONS[group.slug] ?? "grid"} />
                </span>
                <span className="text-lg font-semibold group-hover:text-brand-700">
                  {name(group)}
                </span>
                <span className="ml-auto flex size-8 items-center justify-center rounded-full bg-surface text-muted group-hover:bg-brand-600 group-hover:text-white">
                  <Icon name="arrowRight" className="size-4" />
                </span>
              </Link>
              {(group.children ?? []).length > 0 && (
                <ul className="flex flex-wrap gap-2">
                  {(group.children ?? []).map((leaf) => (
                    <li key={leaf.id}>
                      <Link
                        href={`/search?category=${leaf.slug}`}
                        className="inline-flex min-h-9 items-center rounded-full bg-surface px-3.5 text-sm font-medium text-ink hover:bg-brand-50 hover:text-brand-700"
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

      <section aria-labelledby="how" className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-[var(--radius-card)] bg-card p-5 sm:p-6">
          <h2 id="how" className="mb-5 text-xl font-semibold tracking-tight">
            {t("homeExtra.how")}
          </h2>
          <ol className="grid gap-4 sm:grid-cols-3">
            {steps.map(([icon, title, hint], i) => (
              <li key={title} className="flex flex-col gap-3 rounded-2xl bg-surface p-4">
                <div className="flex items-center justify-between">
                  <span className="flex size-10 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                    <Icon name={icon} />
                  </span>
                  <span className="text-3xl font-semibold text-brand-200">{i + 1}</span>
                </div>
                <p className="font-semibold">{title}</p>
                <p className="text-sm text-muted">{hint}</p>
              </li>
            ))}
          </ol>
        </div>
        <div className="flex flex-col justify-between gap-6 rounded-[var(--radius-card)] bg-ink p-6 text-surface">
          <div className="flex flex-col gap-2">
            <span className="flex size-11 items-center justify-center rounded-full bg-brand-600 text-white">
              <Icon name="building" />
            </span>
            <h2 className="mt-2 text-xl font-semibold tracking-tight">{t("homeExtra.ownerCta")}</h2>
            <p className="text-sm opacity-75">{t("homeExtra.ownerCtaHint")}</p>
          </div>
          <Link href="/owner/onboarding" className={`${buttonClasses("primary", "lg")} w-fit`}>
            {t("homeExtra.ownerCtaButton")}
            <Icon name="arrowRight" className="size-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
