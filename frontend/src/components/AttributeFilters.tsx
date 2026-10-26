import { getTranslations } from "next-intl/server";
import { localized, type Localized } from "@/lib/format";
import { getAll, getParam, type Pair } from "@/lib/search";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

/** A field of a category `attribute_schema` (contracts/attribute-schema.md). */
export type AttrField = {
  key: string;
  type: "integer" | "decimal" | "boolean" | "enum" | "multi_enum" | "text";
  label: Localized;
  unit?: Localized | null;
  min?: number | null;
  max?: number | null;
  options?: { value: string; label: Localized }[] | null;
  filter?: "none" | "exact" | "range" | "any_of";
  order?: number;
};

type Props = { schema: Record<string, unknown>[]; pairs: Pair[]; locale: "sw" | "en" };

/**
 * Filter widgets generated from the category schema, so a new rental type needs no code
 * (Principle I): exact → select or number, range → min/max, any_of → checkboxes. The inputs
 * are named `attr.<key>[.min|.max]` and submit with the surrounding GET form.
 */
export async function AttributeFilters({ schema, pairs, locale }: Props) {
  const t = await getTranslations("filters");
  const fields = (schema as AttrField[])
    .filter((f) => f.filter && f.filter !== "none")
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  if (fields.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      {fields.map((field) => {
        const name = `attr.${field.key}`;
        const label = localized(field.label, locale);
        const unit = field.unit ? ` (${localized(field.unit, locale)})` : "";
        const options = (field.options ?? []).map((o) => ({
          value: o.value,
          label: localized(o.label, locale),
        }));

        if (field.filter === "range") {
          return (
            <fieldset key={field.key} className="grid grid-cols-2 gap-2">
              <legend className="mb-1 text-sm font-medium text-ink">
                {label}
                {unit}
              </legend>
              {(["min", "max"] as const).map((bound) => (
                <Input
                  key={bound}
                  label={t(bound)}
                  name={`${name}.${bound}`}
                  type="number"
                  inputMode="decimal"
                  min={field.min ?? undefined}
                  max={field.max ?? undefined}
                  step={field.type === "integer" ? 1 : "any"}
                  defaultValue={getParam(pairs, `${name}.${bound}`) ?? ""}
                />
              ))}
            </fieldset>
          );
        }

        if (field.filter === "any_of") {
          const chosen = new Set(getAll(pairs, name));
          return (
            <fieldset key={field.key} className="flex flex-col gap-1">
              <legend className="mb-1 text-sm font-medium text-ink">{label}</legend>
              <div className="flex flex-wrap gap-2">
                {options.map((o) => (
                  <label
                    key={o.value}
                    className="inline-flex min-h-10 items-center gap-2 rounded-2xl border border-line bg-surface px-3 text-sm has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50"
                  >
                    <input
                      type="checkbox"
                      name={name}
                      value={o.value}
                      defaultChecked={chosen.has(o.value)}
                      className="size-4 accent-brand-600"
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </fieldset>
          );
        }

        // exact
        if (field.type === "boolean" || field.type === "enum") {
          const choices =
            field.type === "boolean"
              ? [
                  { value: "true", label: t("yes") },
                  { value: "false", label: t("no") },
                ]
              : options;
          return (
            <Select
              key={field.key}
              label={label}
              name={name}
              options={choices}
              placeholder={t("any")}
              defaultValue={getParam(pairs, name) ?? ""}
            />
          );
        }
        return (
          <Input
            key={field.key}
            label={`${label}${unit}`}
            name={name}
            type="number"
            inputMode="numeric"
            defaultValue={getParam(pairs, name) ?? ""}
          />
        );
      })}
    </div>
  );
}
