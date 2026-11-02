"use client";

import { useTranslations } from "next-intl";
import { localized, type Localized } from "@/lib/format";
import type { AttrField } from "./AttributeFilters";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

export type AttrValues = Record<string, unknown>;

type FormField = AttrField & {
  required?: boolean;
  help?: Localized | null;
  group?: Localized | null;
  max_length?: number | null;
};

type Props = {
  schema: Record<string, unknown>[];
  values: AttrValues;
  onChange: (values: AttrValues) => void;
  /** Per-field messages from the API (`INVALID_ATTRIBUTES.details.fields`). */
  errors?: Record<string, string>;
  locale: "sw" | "en";
};

/**
 * Listing details generated from the category `attribute_schema` (contracts/attribute-
 * schema.md), so a new rental type needs no frontend code (Principle I). Browser hints
 * (min/max/required/maxLength) mirror the server rules; the server has the final say.
 */
export function AttributeForm({ schema, values, onChange, errors = {}, locale }: Props) {
  const t = useTranslations("attributes");
  const fields = (schema as FormField[]).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const groups = new Map<string, FormField[]>();
  for (const field of fields) {
    const name = field.group ? localized(field.group, locale) : "";
    groups.set(name, [...(groups.get(name) ?? []), field]);
  }

  const set = (key: string, value: unknown) => {
    const next = { ...values };
    if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  };

  const render = (field: FormField) => {
    const label = `${localized(field.label, locale)}${field.unit ? ` (${localized(field.unit, locale)})` : ""}${
      field.required ? " *" : ""
    }`;
    const hint = field.help ? localized(field.help, locale) : undefined;
    const error = errors[field.key] ?? null;
    const value = values[field.key];
    const options = (field.options ?? []).map((o) => ({
      value: o.value,
      label: localized(o.label, locale),
    }));

    switch (field.type) {
      case "integer":
      case "decimal":
        return (
          <Input
            key={field.key}
            label={label}
            hint={hint}
            error={error}
            type="number"
            inputMode={field.type === "integer" ? "numeric" : "decimal"}
            step={field.type === "integer" ? 1 : "any"}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            required={field.required}
            value={typeof value === "number" ? String(value) : ""}
            onChange={(e) => set(field.key, e.target.value === "" ? undefined : Number(e.target.value))}
          />
        );
      case "boolean":
        return (
          <Select
            key={field.key}
            label={label}
            error={error}
            required={field.required}
            placeholder={field.required ? "" : t("notSet")}
            value={value === true ? "true" : value === false ? "false" : ""}
            onChange={(e) =>
              set(field.key, e.target.value === "" ? undefined : e.target.value === "true")
            }
            options={[
              { value: "true", label: t("yes") },
              { value: "false", label: t("no") },
            ]}
          />
        );
      case "enum":
        return (
          <Select
            key={field.key}
            label={label}
            error={error}
            required={field.required}
            placeholder={field.required ? "" : t("notSet")}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => set(field.key, e.target.value || undefined)}
            options={options}
          />
        );
      case "multi_enum": {
        const chosen = Array.isArray(value) ? (value as string[]) : [];
        return (
          <fieldset key={field.key} className="flex flex-col gap-1">
            <legend className="mb-1 text-sm font-medium text-ink">{label}</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {options.map((o) => (
                <label key={o.value} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    className="size-5 accent-brand-600"
                    checked={chosen.includes(o.value)}
                    onChange={(e) =>
                      set(
                        field.key,
                        e.target.checked
                          ? [...chosen, o.value]
                          : chosen.filter((v) => v !== o.value),
                      )
                    }
                  />
                  {o.label}
                </label>
              ))}
            </div>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
          </fieldset>
        );
      }
      default:
        return (
          <Input
            key={field.key}
            label={label}
            hint={hint}
            error={error}
            required={field.required}
            maxLength={field.max_length ?? 500}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => set(field.key, e.target.value.trim() ? e.target.value : undefined)}
          />
        );
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {[...groups.entries()].map(([group, list]) => (
        <section key={group || "_"} className="flex flex-col gap-3">
          {group && <h3 className="text-sm font-semibold text-muted">{group}</h3>}
          {list.map(render)}
        </section>
      ))}
      {errors._ && (
        <p role="alert" className="text-sm text-danger">
          {errors._}
        </p>
      )}
    </div>
  );
}
