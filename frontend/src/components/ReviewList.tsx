import type { Schemas } from "@/lib/api/client";
import { formatDate } from "@/lib/format";

type Review = Schemas["ReviewOut"] & { about?: "renter" | "owner" };

export function ReviewList({
  reviews,
  locale,
  aboutLabel,
}: {
  reviews: Review[];
  locale: "sw" | "en";
  aboutLabel?: (about: "renter" | "owner") => string;
}) {
  return (
    <ul className="flex flex-col gap-3">
      {reviews.map((r, i) => (
        <li key={`${r.author}-${r.created_at}-${i}`} className="flex flex-col gap-0.5 text-sm">
          <p className="font-medium text-ink">
            <span className="text-amber-500" aria-label={`${r.rating}/5`}>
              {"★".repeat(r.rating)}
              <span className="text-line">{"★".repeat(5 - r.rating)}</span>
            </span>{" "}
            · {r.author}
          </p>
          <p className="text-xs text-muted">
            {formatDate(r.created_at, locale)}
            {r.about && aboutLabel ? ` · ${aboutLabel(r.about)}` : ""}
          </p>
          {r.comment && <p className="whitespace-pre-line text-ink">{r.comment}</p>}
        </li>
      ))}
    </ul>
  );
}
