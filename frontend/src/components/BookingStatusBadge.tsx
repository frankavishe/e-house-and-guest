import { useTranslations } from "next-intl";
import type { BookingStatus } from "@/lib/api/bookings";
import { Badge } from "./ui/Badge";

const TONES = {
  requested: "warning",
  awaiting_payment: "warning",
  confirmed: "success",
  in_progress: "brand",
  completed: "neutral",
  cancelled: "danger",
  disputed: "danger",
} as const;

export function BookingStatusBadge({ status }: { status: BookingStatus }) {
  const t = useTranslations("bookingStatus");
  return <Badge tone={TONES[status]}>{t(status)}</Badge>;
}
