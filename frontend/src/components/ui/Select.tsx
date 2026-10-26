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
        className={`h-12 rounded-2xl border bg-card px-4 text-base text-ink focus:border-brand-400 focus:bg-surface focus:outline-none focus:ring-4 focus:ring-brand-100 ${
          error ? "border-danger" : "border-transparent"
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
