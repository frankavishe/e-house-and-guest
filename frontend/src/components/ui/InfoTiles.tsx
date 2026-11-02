import type { ReactNode } from "react";

type Tile = { label: ReactNode; value: ReactNode; mono?: boolean; wide?: boolean };

/** Small label/value tiles, the detail grid inside a list card. Falsy entries are skipped. */
export function InfoTiles({ tiles }: { tiles: (Tile | "" | false | null | undefined)[] }) {
  return (
    <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
      {tiles
        .filter((tile): tile is Tile => Boolean(tile))
        .map(({ label, value, mono, wide }, i) => (
          <div
            key={i}
            className={`min-w-0 rounded-2xl bg-surface p-3 ${wide ? "col-span-2 sm:col-span-3" : ""}`}
          >
            <dt className="text-xs text-muted">{label}</dt>
            <dd className={`mt-0.5 break-words font-medium text-ink ${mono ? "font-mono" : ""}`}>
              {value}
            </dd>
          </div>
        ))}
    </dl>
  );
}
