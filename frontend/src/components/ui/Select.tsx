"use client";

import { useId, type SelectHTMLAttributes } from "react";

export type Option = { value: string; label: string };

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> & {
  label: string;
  options: Option[];
  placeholder?: string;
  error?: string | null;
};

/** Native select: smallest JS, best on low-end phones. */
export function Select({ label, options, placeholder, error, id, className = "", ...rest }: Props) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={selectId} className="text-sm font-medium text-ink">
        {label}
      </label>
      <select
        id={selectId}
        aria-invalid={error ? true : undefined}
        className={`h-12 rounded-lg border bg-surface px-3 text-base text-ink ${
          error ? "border-danger" : "border-line"
        } ${className}`}
        {...rest}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
