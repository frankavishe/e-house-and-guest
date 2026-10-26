"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { useRouter } from "@/i18n/navigation";
import { withParams, type Pair } from "@/lib/search";
import { Icon } from "./icons";
import { Button } from "./ui/Button";
import { Sheet } from "./ui/Sheet";

/** A GET form that leaves blank fields out of the URL. Without JavaScript it still submits
 * (the search page ignores blank values). */
export function CleanGetForm({
  action,
  children,
  className = "",
}: {
  action: string;
  children: ReactNode;
  className?: string;
}) {
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    for (const el of Array.from(event.currentTarget.elements)) {
      if (
        (el instanceof HTMLInputElement || el instanceof HTMLSelectElement) &&
        el.name &&
        el.value.trim() === "" &&
        !(el instanceof HTMLInputElement && el.type === "checkbox")
      ) {
        el.disabled = true;
      }
    }
  }
  return (
    <form action={action} method="get" onSubmit={onSubmit} className={className}>
      {children}
    </form>
  );
}

/** "Filters" button opening a bottom sheet with the (server-rendered) filter form. */
export function FiltersSheet({
  label,
  title,
  closeLabel,
  activeCount,
  children,
}: {
  label: string;
  title: string;
  closeLabel: string;
  activeCount: number;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)} aria-haspopup="dialog" className="bg-surface">
        <Icon name="filter" className="size-4" />
        {label}
        {activeCount > 0 && (
          <span className="rounded-full bg-brand-600 px-1.5 text-xs text-white">{activeCount}</span>
        )}
      </Button>
      <Sheet open={open} onClose={() => setOpen(false)} title={title} closeLabel={closeLabel}>
        {children}
      </Sheet>
    </>
  );
}

/** Sort order; changes the URL (and resets to page 1). */
export function SortSelect({
  label,
  options,
  value,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
}) {
  const router = useRouter();
  const search = useSearchParams();
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <span className="sr-only pl-2 sm:not-sr-only">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => {
          const pairs = Array.from(search.entries()) as Pair[];
          router.push(`/search${withParams(pairs, { sort: e.target.value })}`);
        }}
        className="h-10 rounded-full border-0 bg-surface px-4 text-sm font-medium"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
