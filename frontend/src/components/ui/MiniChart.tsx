// Small charts drawn with divs: no chart library on the page (Principle VI). The numbers they
// show are always also given as text nearby, so the bars themselves are aria-hidden.

type Point = { label: string; value: number };

/** Vertical bars; the last one (the current period) is highlighted. */
export function MiniBars({ data, className = "" }: { data: Point[]; className?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div aria-hidden className={`flex items-end gap-1.5 ${className}`}>
      {data.map((d, i) => (
        <div key={d.label} className="flex flex-col items-center gap-1">
          <div className="flex h-12 w-4 items-end">
            <div
              className={`w-full rounded-full ${i === data.length - 1 ? "bg-brand-500" : "bg-brand-200"}`}
              style={{ height: `${Math.max(8, (d.value / max) * 100)}%` }}
            />
          </div>
          <span className="text-[9px] leading-none text-muted">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

/** One dot per value at its height, like a sparse scatter. */
export function MiniDots({ data, className = "" }: { data: Point[]; className?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div aria-hidden className={`flex items-end gap-2 ${className}`}>
      {data.map((d, i) => (
        <div key={d.label} className="flex flex-col items-center gap-1">
          <div className="relative h-12 w-2">
            <span
              className={`absolute left-0 size-2 rounded-full ${
                i === data.length - 1 ? "bg-brand-600" : "bg-brand-300"
              }`}
              style={{ bottom: `calc(${(d.value / max) * 100}% - 4px)` }}
            />
          </div>
          <span className="text-[9px] leading-none text-muted">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Horizontal share bar with a legend, e.g. bookings by status. */
export function ShareBar({
  parts,
}: {
  parts: { label: string; value: number; className: string }[];
}) {
  const total = parts.reduce((sum, p) => sum + p.value, 0) || 1;
  return (
    <div className="flex flex-col gap-3">
      <div aria-hidden className="flex h-3 gap-0.5 overflow-hidden rounded-full bg-surface">
        {parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <div
              key={p.label}
              className={`rounded-full ${p.className}`}
              style={{ width: `${(p.value / total) * 100}%` }}
            />
          ))}
      </div>
      <ul className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
        {parts.map((p) => (
          <li key={p.label} className="flex items-center gap-2">
            <span aria-hidden className={`size-2.5 shrink-0 rounded-full ${p.className}`} />
            <span className="truncate text-muted">{p.label}</span>
            <span className="ml-auto font-semibold tabular-nums">{p.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
