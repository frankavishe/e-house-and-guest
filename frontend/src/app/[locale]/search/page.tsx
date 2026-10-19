import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AttributeFilters } from "@/components/AttributeFilters";
import { ListingCard } from "@/components/ListingCard";
import { Pagination } from "@/components/Pagination";
import { PeriodFields } from "@/components/PeriodFields";
import { CleanGetForm, FiltersSheet, SortSelect } from "@/components/SearchControls";
import { SearchMapLoader } from "@/components/SearchMapLoader";
import { buttonClasses, Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Link } from "@/i18n/navigation";
import {
  flattenCategories,
  getCategories,
  getCategory,
  getLocations,
  searchListings,
} from "@/lib/api/queries";
import { formatTZS, localized } from "@/lib/format";
import {
  cleanParams,
  getParam,
  periodQuery,
  toApiPairs,
  withParams,
  type RawParams,
} from "@/lib/search";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<RawParams> };

const SORTS = ["newest", "price_asc", "price_desc", "rating"] as const;
const UI_KEYS = new Set(["sort", "page", "view", "bbox"]);
const TILE_URL =
  process.env.NEXT_PUBLIC_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "search" });
  return { title: t("title") };
}

export default async function SearchPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const pairs = cleanParams(query);
  const slug = getParam(pairs, "category");
  const regionId = Number(getParam(pairs, "region")) || undefined;
  const view = getParam(pairs, "view") === "map" ? "map" : "list";
  const sort = getParam(pairs, "sort") ?? "newest";

  const [t, categories, regions, districts, category, { page, error }] = await Promise.all([
    getTranslations(),
    getCategories(),
    getLocations(),
    regionId ? getLocations(regionId) : Promise.resolve([]),
    slug ? getCategory(slug) : Promise.resolve(null),
    searchListings(toApiPairs(pairs)),
  ]);

  const name = (node: { name: { sw: string; en: string } }) => localized(node.name, locale);
  const carry = periodQuery(pairs);
  const items = page?.items ?? [];
  const activeFilters = pairs.filter(([k]) => !UI_KEYS.has(k)).length;
  const heading = category ? name(category) : t("search.title");

  const filters = (
    <CleanGetForm action={`/${locale}/search`} className="flex flex-col gap-4">
      {(["sort", "view"] as const).map((key) =>
        getParam(pairs, key) ? (
          <input key={key} type="hidden" name={key} value={getParam(pairs, key)} />
        ) : null,
      )}
      <Input
        label={t("home.whatLabel")}
        name="q"
        type="search"
        maxLength={100}
        defaultValue={getParam(pairs, "q") ?? ""}
      />
      <Select
        label={t("filters.category")}
        name="category"
        placeholder={t("filters.allCategories")}
        options={flattenCategories(categories, name)}
        defaultValue={slug ?? ""}
      />
      <div className="grid grid-cols-2 gap-2">
        <Select
          label={t("filters.region")}
          name="region"
          placeholder={t("filters.allRegions")}
          options={regions.map((r) => ({ value: String(r.id), label: r.name }))}
          defaultValue={getParam(pairs, "region") ?? ""}
        />
        {districts.length > 0 && (
          <Select
            label={t("filters.district")}
            name="district"
            placeholder={t("filters.allDistricts")}
            options={districts.map((d) => ({ value: String(d.id), label: d.name }))}
            defaultValue={getParam(pairs, "district") ?? ""}
          />
        )}
      </div>
      <PeriodFields
        mode={category?.booking_mode}
        defaultUnit={category?.default_unit}
        pairs={pairs}
      />
      <fieldset className="grid grid-cols-2 gap-2">
        <legend className="mb-1 text-sm font-medium text-ink">{t("filters.price")}</legend>
        <Input
          label={t("filters.min")}
          name="price_min"
          type="number"
          inputMode="numeric"
          min={0}
          defaultValue={getParam(pairs, "price_min") ?? ""}
        />
        <Input
          label={t("filters.max")}
          name="price_max"
          type="number"
          inputMode="numeric"
          min={0}
          defaultValue={getParam(pairs, "price_max") ?? ""}
        />
      </fieldset>
      {category?.is_leaf ? (
        <AttributeFilters schema={category.attribute_schema} pairs={pairs} locale={locale} />
      ) : (
        <p className="text-sm text-muted">{t("filters.pickCategoryForMore")}</p>
      )}
      <div className="sticky bottom-0 flex gap-2 bg-surface pt-2">
        <Link href="/search" className={buttonClasses("secondary")}>
          {t("filters.clear")}
        </Link>
        <Button type="submit" full>
          {t("filters.apply")}
        </Button>
      </div>
    </CleanGetForm>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-ink sm:text-2xl">{heading}</h1>
        {page && (
          <p className="text-sm text-muted" aria-live="polite">
            {t("search.resultCount", { count: page.total })}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <FiltersSheet
          label={t("filters.title")}
          title={t("filters.title")}
          closeLabel={t("common.close")}
          activeCount={activeFilters}
        >
          {filters}
        </FiltersSheet>
        <SortSelect
          label={t("search.sortLabel")}
          value={sort}
          options={SORTS.map((s) => ({ value: s, label: t(`search.sort.${s}`) }))}
        />
        <Link
          href={`/search${withParams(pairs, { view: view === "map" ? null : "map" })}`}
          className={`${buttonClasses("ghost")} ml-auto`}
        >
          {view === "map" ? t("search.showList") : t("search.showMap")}
        </Link>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
        >
          {error.status === 404
            ? t("search.unknownCategory")
            : error.message || t("errors.generic")}
        </p>
      )}

      {view === "map" && (
        <SearchMapLoader
          bbox={getParam(pairs, "bbox")}
          tileUrl={TILE_URL}
          attribution={t("map.attribution")}
          items={items
            .filter((i) => i.lat != null && i.lng != null)
            .map((i) => ({
              id: i.id,
              title: i.title,
              lat: i.lat as number,
              lng: i.lng as number,
              href: `/l/${i.id}${carry}`,
              price: formatTZS(i.total_tzs ?? i.base_price?.amount_tzs ?? 0),
            }))}
        />
      )}

      {getParam(pairs, "bbox") && (
        <p className="text-sm text-muted">
          {t("search.inMapArea")}{" "}
          <Link
            href={`/search${withParams(pairs, { bbox: null })}`}
            className="text-brand-700 underline"
          >
            {t("search.clearMapArea")}
          </Link>
        </p>
      )}

      {page && items.length === 0 && !error && (
        <div className="rounded-xl border border-dashed border-line p-6 text-center">
          <p className="font-medium text-ink">{t("search.noResults")}</p>
          <p className="mt-1 text-sm text-muted">{t("search.noResultsHint")}</p>
        </div>
      )}

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((listing, index) => (
          <li key={listing.id}>
            <ListingCard listing={listing} periodQuery={carry} priority={index < 2} />
          </li>
        ))}
      </ul>

      {page && (
        <Pagination pairs={pairs} page={page.page} pageSize={page.page_size} total={page.total} />
      )}
    </div>
  );
}
