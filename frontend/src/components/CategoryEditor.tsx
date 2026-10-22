"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { localized } from "@/lib/format";
import { AttributeForm, type AttrValues } from "./AttributeForm";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Category = Schemas["AdminCategoryOut"];
type BookingMode = NonNullable<Category["booking_mode"]>;
type Unit = NonNullable<Schemas["AdminCategoryIn"]["price_units"]>[number];
type FieldType = "integer" | "decimal" | "boolean" | "enum" | "multi_enum" | "text";
type Filter = "none" | "exact" | "range" | "any_of";
type Locale = "sw" | "en";

const MODES: BookingMode[] = ["DATE_RANGE", "TIME_SLOT", "LEASE", "QUANTITY"];
const UNITS: Unit[] = ["hour", "night", "day", "week", "month", "item_day"];
const TYPES: FieldType[] = ["integer", "decimal", "boolean", "enum", "multi_enum", "text"];
// Mirrors ALLOWED_FILTERS in backend/app/catalog/attributes.py; the server re-checks.
const FILTERS: Record<FieldType, Filter[]> = {
  integer: ["none", "exact", "range"],
  decimal: ["none", "range"],
  boolean: ["none", "exact"],
  enum: ["none", "exact", "any_of"],
  multi_enum: ["none", "any_of"],
  text: ["none"],
};

const EDITED_KEYS = [
  "key",
  "type",
  "label",
  "unit",
  "required",
  "min",
  "max",
  "max_length",
  "options",
  "filter",
  "show_on_card",
  "order",
];

type OptionDraft = { value: string; sw: string; en: string };
type FieldDraft = {
  /** Fields the editor does not show (help, group) are kept as they were. */
  rest: Record<string, unknown>;
  key: string;
  type: FieldType;
  sw: string;
  en: string;
  unitSw: string;
  unitEn: string;
  required: boolean;
  min: string;
  max: string;
  maxLength: string;
  options: OptionDraft[];
  filter: Filter;
  showOnCard: boolean;
};

type L = { sw?: string; en?: string } | undefined;

function toDraft(raw: Record<string, unknown>): FieldDraft {
  const { key, type, label, unit, required, min, max, max_length, options, filter, show_on_card } =
    raw as Record<string, unknown> & { label?: L; unit?: L };
  const rest = { ...raw };
  for (const k of EDITED_KEYS) delete rest[k];
  return {
    rest,
    key: String(key ?? ""),
    type: (type as FieldType) ?? "text",
    sw: label?.sw ?? "",
    en: label?.en ?? "",
    unitSw: unit?.sw ?? "",
    unitEn: unit?.en ?? "",
    required: Boolean(required),
    min: min == null ? "" : String(min),
    max: max == null ? "" : String(max),
    maxLength: max_length == null ? "" : String(max_length),
    options: ((options as { value: string; label: L }[] | undefined) ?? []).map((o) => ({
      value: o.value,
      sw: o.label?.sw ?? "",
      en: o.label?.en ?? "",
    })),
    filter: (filter as Filter) ?? "none",
    showOnCard: Boolean(show_on_card),
  };
}

const blankField = (): FieldDraft => toDraft({ type: "text" });

function toSchemaField(f: FieldDraft, index: number): Record<string, unknown> {
  const numeric = f.type === "integer" || f.type === "decimal";
  const choice = f.type === "enum" || f.type === "multi_enum";
  return {
    ...f.rest,
    key: f.key.trim(),
    type: f.type,
    label: { sw: f.sw, en: f.en },
    ...(f.unitSw || f.unitEn ? { unit: { sw: f.unitSw, en: f.unitEn } } : {}),
    required: f.required,
    ...(numeric && f.min !== "" ? { min: Number(f.min) } : {}),
    ...(numeric && f.max !== "" ? { max: Number(f.max) } : {}),
    ...(f.type === "text" && f.maxLength !== "" ? { max_length: Number(f.maxLength) } : {}),
    ...(choice
      ? {
          options: f.options.map((o) => ({ value: o.value.trim(), label: { sw: o.sw, en: o.en } })),
        }
      : {}),
    filter: FILTERS[f.type].includes(f.filter) ? f.filter : "none",
    show_on_card: f.showOnCard,
    order: index + 1,
  };
}

const pct = (bps: number) => String(bps / 100);
const bps = (value: string) => Math.round(Number(value || 0) * 100);

type Props = {
  locale: Locale;
  /** The category to edit; omitted when creating one. */
  category?: Category;
  /** Groups a new category can be placed under. */
  groups: Category[];
};

/**
 * Category and field editor (US7-AS1, FR-006): an admin adds a rental type with its fields,
 * and owners can list it straight away. The preview shows the owner form and the filters
 * renters will get, built from the same schema.
 */
export function CategoryEditor({ locale, category, groups }: Props) {
  const t = useTranslations("adminCategories");
  const tr = useTranslations();
  const router = useRouter();
  const creating = !category;

  const [slug, setSlug] = useState(category?.slug ?? "");
  const [parentId, setParentId] = useState(category?.parent_id ?? "");
  const [nameSw, setNameSw] = useState(category?.name.sw ?? "");
  const [nameEn, setNameEn] = useState(category?.name.en ?? "");
  const [mode, setMode] = useState<BookingMode | "">(category?.booking_mode ?? "DATE_RANGE");
  const [units, setUnits] = useState<Unit[]>((category?.price_units as Unit[]) ?? ["night"]);
  const [defaultUnit, setDefaultUnit] = useState<Unit | "">(
    (category?.default_unit as Unit | null) ?? "night",
  );
  const [commission, setCommission] = useState(pct(category?.commission_bps ?? 1000));
  const [fee, setFee] = useState(pct(category?.renter_fee_bps ?? 0));
  const [active, setActive] = useState(category?.is_active ?? true);
  const [sortOrder, setSortOrder] = useState(String(category?.sort_order ?? 0));
  const [fields, setFields] = useState<FieldDraft[]>(
    (category?.attribute_schema ?? []).map((f) => toDraft(f)),
  );
  const [preview, setPreview] = useState<AttrValues>({});
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const isLeaf = mode !== "";
  const schema = useMemo(() => fields.map(toSchemaField), [fields]);

  const update = (i: number, patch: Partial<FieldDraft>) =>
    setFields((all) => all.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const move = (i: number, by: -1 | 1) =>
    setFields((all) => {
      const next = [...all];
      const j = i + by;
      if (j < 0 || j >= next.length) return all;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const toggleUnit = (unit: Unit) => {
    const next = units.includes(unit) ? units.filter((u) => u !== unit) : [...units, unit];
    setUnits(next);
    if (!next.includes(defaultUnit as Unit)) setDefaultUnit(next[0] ?? "");
  };

  async function save() {
    setBusy(true);
    setError(null);
    setProblems([]);
    setSaved(false);
    const common = {
      name: { sw: nameSw, en: nameEn },
      price_units: isLeaf ? units : [],
      default_unit: isLeaf && defaultUnit ? defaultUnit : null,
      attribute_schema: isLeaf ? schema : [],
      commission_bps: bps(commission),
      renter_fee_bps: bps(fee),
      is_active: active,
      sort_order: Number(sortOrder || 0),
    };
    try {
      const { data, error: err } = creating
        ? await api.POST("/api/v1/admin/categories", {
            body: {
              ...common,
              slug: slug.trim(),
              parent_id: parentId || null,
              booking_mode: mode || null,
            },
          })
        : await api.PATCH("/api/v1/admin/categories/{category_id}", {
            params: { path: { category_id: category.id } },
            body: common,
          });
      if (err || !data) {
        const e = apiError(err);
        setError(e?.message ?? tr("errors.generic"));
        const details = e?.details ?? {};
        const list = Array.isArray(details.problems) ? (details.problems as string[]) : [];
        if (typeof details.field === "string") list.push(t("problemField", { key: details.field }));
        setProblems(list);
      } else if (creating) {
        router.push(`/admin/categories/${data.id}`);
      } else {
        setSaved(true);
        router.refresh();
      }
    } catch {
      setError(tr("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const filterable = schema.filter((f) => f.filter !== "none");

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
        <h2 className="font-semibold text-ink">{t("basics")}</h2>
        <Input
          label={t("slug")}
          hint={creating ? t("slugHint") : t("fixedHint")}
          value={slug}
          disabled={!creating}
          pattern="[a-z][a-z0-9\-]{1,59}"
          onChange={(e) => setSlug(e.target.value)}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label={t("nameSw")} value={nameSw} onChange={(e) => setNameSw(e.target.value)} />
          <Input label={t("nameEn")} value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
        </div>
        <Select
          label={t("parent")}
          disabled={!creating}
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
          options={[
            { value: "", label: t("topLevel") },
            ...groups.map((g) => ({
              value: g.id,
              label: `${g.path} · ${localized(g.name, locale)}`,
            })),
          ]}
        />
        <Select
          label={t("bookingMode")}
          disabled={!creating}
          value={mode}
          onChange={(e) => setMode(e.target.value as BookingMode | "")}
          options={[
            { value: "", label: t("group") },
            ...MODES.map((m) => ({ value: m, label: t(`mode_${m}`) })),
          ]}
        />
        {isLeaf && (
          <>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium text-ink">{t("priceUnits")}</legend>
              <div className="flex flex-wrap gap-3">
                {UNITS.map((u) => (
                  <label key={u} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={units.includes(u)}
                      onChange={() => toggleUnit(u)}
                    />
                    {tr(`units.${u}`)}
                  </label>
                ))}
              </div>
            </fieldset>
            <Select
              label={t("defaultUnit")}
              value={defaultUnit}
              onChange={(e) => setDefaultUnit(e.target.value as Unit)}
              options={units.map((u) => ({ value: u, label: tr(`units.${u}`) }))}
            />
          </>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <Input
            label={t("commission")}
            hint={t("ratesHint")}
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            step={0.01}
            value={commission}
            onChange={(e) => setCommission(e.target.value)}
          />
          <Input
            label={t("renterFee")}
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            step={0.01}
            value={fee}
            onChange={(e) => setFee(e.target.value)}
          />
          <Input
            label={t("sortOrder")}
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t("active")}
        </label>
      </section>

      {isLeaf && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold text-ink">{t("fields")}</h2>
            <Button variant="secondary" onClick={() => setFields((all) => [...all, blankField()])}>
              {t("addField")}
            </Button>
          </div>
          {fields.length === 0 && <p className="text-sm text-muted">{t("noFields")}</p>}
          {category && category.listing_count > 0 && (
            <p className="text-sm text-muted">
              {t("inUseHint", { count: category.listing_count })}
            </p>
          )}
          {fields.map((f, i) => (
            <FieldEditor
              key={i}
              field={f}
              index={i}
              last={i === fields.length - 1}
              onChange={(patch) => update(i, patch)}
              onMove={(by) => move(i, by)}
              onRemove={() => setFields((all) => all.filter((_, j) => j !== i))}
            />
          ))}
        </section>
      )}

      {isLeaf && schema.length > 0 && (
        <section className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-3 rounded-xl border border-dashed border-line p-4">
            <h2 className="font-semibold text-ink">{t("previewForm")}</h2>
            <AttributeForm schema={schema} values={preview} onChange={setPreview} locale={locale} />
          </div>
          <div className="flex flex-col gap-3 rounded-xl border border-dashed border-line p-4">
            <h2 className="font-semibold text-ink">{t("previewFilters")}</h2>
            {filterable.length === 0 ? (
              <p className="text-sm text-muted">{t("noFilters")}</p>
            ) : (
              <ul className="flex flex-col gap-1 text-sm">
                {filterable.map((f) => (
                  <li key={String(f.key)}>
                    <span className="font-medium text-ink">
                      {localized(f.label as { sw: string; en: string }, locale)}
                    </span>{" "}
                    <span className="text-muted">· {t(`filter_${f.filter as Filter}`)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      <div className="flex flex-col gap-2">
        <div>
          <Button loading={busy} onClick={save}>
            {creating ? t("create") : t("save")}
          </Button>
        </div>
        {saved && (
          <p role="status" className="text-sm text-brand-700">
            {t("saved")}
          </p>
        )}
        {error && (
          <div role="alert" className="text-sm text-danger">
            <p>{error}</p>
            {problems.length > 0 && (
              <ul className="list-disc pl-5">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function FieldEditor({
  field: f,
  index,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  field: FieldDraft;
  index: number;
  last: boolean;
  onChange: (patch: Partial<FieldDraft>) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("adminCategories");
  const numeric = f.type === "integer" || f.type === "decimal";
  const choice = f.type === "enum" || f.type === "multi_enum";
  const setOption = (i: number, patch: Partial<OptionDraft>) =>
    onChange({ options: f.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) });

  return (
    <fieldset className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
      <legend className="px-1 text-sm font-medium text-muted">
        {t("fieldN", { n: index + 1 })}
      </legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          label={t("key")}
          hint={t("keyHint")}
          value={f.key}
          pattern="[a-z][a-z0-9_]{1,39}"
          onChange={(e) => onChange({ key: e.target.value })}
        />
        <Select
          label={t("type")}
          value={f.type}
          onChange={(e) => {
            const type = e.target.value as FieldType;
            onChange({ type, filter: FILTERS[type].includes(f.filter) ? f.filter : "none" });
          }}
          options={TYPES.map((ty) => ({ value: ty, label: t(`type_${ty}`) }))}
        />
        <Input
          label={t("labelSw")}
          value={f.sw}
          onChange={(e) => onChange({ sw: e.target.value })}
        />
        <Input
          label={t("labelEn")}
          value={f.en}
          onChange={(e) => onChange({ en: e.target.value })}
        />
        {numeric && (
          <>
            <Input
              label={t("unitSw")}
              value={f.unitSw}
              onChange={(e) => onChange({ unitSw: e.target.value })}
            />
            <Input
              label={t("unitEn")}
              value={f.unitEn}
              onChange={(e) => onChange({ unitEn: e.target.value })}
            />
            <Input
              label={t("min")}
              type="number"
              step="any"
              value={f.min}
              onChange={(e) => onChange({ min: e.target.value })}
            />
            <Input
              label={t("max")}
              type="number"
              step="any"
              value={f.max}
              onChange={(e) => onChange({ max: e.target.value })}
            />
          </>
        )}
        {f.type === "text" && (
          <Input
            label={t("maxLength")}
            type="number"
            min={1}
            max={500}
            value={f.maxLength}
            onChange={(e) => onChange({ maxLength: e.target.value })}
          />
        )}
        <Select
          label={t("filter")}
          value={f.filter}
          onChange={(e) => onChange({ filter: e.target.value as Filter })}
          options={FILTERS[f.type].map((fl) => ({ value: fl, label: t(`filter_${fl}`) }))}
        />
      </div>
      {choice && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-ink">{t("options")}</p>
          {f.options.map((o, i) => (
            <div
              key={i}
              className="flex flex-col gap-2 rounded-lg border border-line p-2 sm:grid sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end sm:border-0 sm:p-0"
            >
              <Input
                label={t("optionValue")}
                className="w-full min-w-0"
                value={o.value}
                onChange={(e) => setOption(i, { value: e.target.value })}
              />
              <Input
                label={t("labelSw")}
                className="w-full min-w-0"
                value={o.sw}
                onChange={(e) => setOption(i, { sw: e.target.value })}
              />
              <Input
                label={t("labelEn")}
                className="w-full min-w-0"
                value={o.en}
                onChange={(e) => setOption(i, { en: e.target.value })}
              />
              <Button
                className="self-end"
                variant="ghost"
                aria-label={t("removeOption")}
                onClick={() => onChange({ options: f.options.filter((_, j) => j !== i) })}
              >
                ×
              </Button>
            </div>
          ))}
          <div>
            <Button
              variant="secondary"
              onClick={() => onChange({ options: [...f.options, { value: "", sw: "", en: "" }] })}
            >
              {t("addOption")}
            </Button>
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={f.required}
            onChange={(e) => onChange({ required: e.target.checked })}
          />
          {t("required")}
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={f.showOnCard}
            onChange={(e) => onChange({ showOnCard: e.target.checked })}
          />
          {t("showOnCard")}
        </label>
        <span className="ml-auto flex gap-1">
          <Button variant="ghost" disabled={index === 0} onClick={() => onMove(-1)}>
            {t("up")}
          </Button>
          <Button variant="ghost" disabled={last} onClick={() => onMove(1)}>
            {t("down")}
          </Button>
          <Button variant="ghost" onClick={onRemove}>
            {t("removeField")}
          </Button>
        </span>
      </div>
    </fieldset>
  );
}
