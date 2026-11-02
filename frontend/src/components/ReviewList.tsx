import type { Schemas } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { Avatar } from "./ui/Avatar";

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
    <ul className="flex flex-col gap-2">
      {reviews.map((r, i) => (
        <li
          key={`${r.author}-${r.created_at}-${i}`}
          className="flex gap-3 rounded-2xl bg-surface p-4 text-sm"
        >
          <Avatar name={r.author} size="sm" />
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="flex flex-wrap items-center gap-x-2 font-medium text-ink">
              {r.author}
              <span className="text-accent-500" aria-label={`${r.rating}/5`}>
                {"★".repeat(r.rating)}
                <span className="text-line">{"★".repeat(5 - r.rating)}</span>
              </span>
            </p>
            <p className="text-xs text-muted">
              {formatDate(r.created_at, locale)}
              {r.about && aboutLabel ? ` · ${aboutLabel(r.about)}` : ""}
            </p>
            {r.comment && <p className="mt-1 whitespace-pre-line text-ink">{r.comment}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
