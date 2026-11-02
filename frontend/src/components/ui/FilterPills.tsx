import { Link } from "@/i18n/navigation";

type Pill = { href: string; label: string; current: boolean };

/** Row of status filters as pills; the current one is violet, like the sidebar. */
export function FilterPills({ label, pills }: { label: string; pills: Pill[] }) {
  return (
    <nav aria-label={label} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
      {pills.map((p) => (
        <Link
          key={p.href}
          href={p.href}
          aria-current={p.current ? "page" : undefined}
          className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            p.current ? "bg-brand-600 text-white shadow-soft" : "bg-card text-ink hover:bg-brand-50"
          }`}
        >
          {p.label}
        </Link>
      ))}
    </nav>
  );
}
