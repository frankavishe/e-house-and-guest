import { useTranslations } from "next-intl";
import type { Earnings } from "@/lib/api/owner";
import { Badge } from "./ui/Badge";

type Status = Earnings["items"][number]["status"];

const TONES = {
  upcoming: "neutral",
  available: "brand",
  pending: "warning",
  processing: "warning",
  paid: "success",
  failed: "danger",
} as const;

/** Earning or payout status: upcoming → available → pending/processing → paid | failed. */
export function PayoutStatusBadge({ status }: { status: Status }) {
  const t = useTranslations("payoutStatus");
  return <Badge tone={TONES[status]}>{t(status)}</Badge>;
}
