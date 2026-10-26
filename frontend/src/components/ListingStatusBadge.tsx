import { useTranslations } from "next-intl";
import type { OwnerListing } from "@/lib/api/owner";
import { Badge } from "./ui/Badge";

const TONES = {
  draft: "neutral",
  pending_review: "warning",
  active: "success",
  paused: "neutral",
  rejected: "danger",
  suspended: "danger",
  deleted: "neutral",
} as const;

/** Listing status, plus "changes in review" / "changes rejected" for live listings. */
export function ListingStatusBadge({ listing }: { listing: Pick<OwnerListing, "status" | "review_state"> }) {
  const t = useTranslations("listingStatus");
  return (
    <span className="flex flex-wrap gap-1">
      <Badge tone={TONES[listing.status]}>{t(listing.status)}</Badge>
      {listing.review_state !== "none" && (
        <Badge tone={listing.review_state === "pending" ? "warning" : "danger"}>
          {t(`review_${listing.review_state}`)}
        </Badge>
      )}
    </span>
  );
}
