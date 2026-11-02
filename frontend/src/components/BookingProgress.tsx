import { useTranslations } from "next-intl";
import type { BookingStatus } from "@/lib/api/bookings";
import { Timeline } from "./ui/Timeline";

const FLOW = ["requested", "awaiting_payment", "confirmed", "in_progress", "completed"] as const;

/** Where a booking is on its way from request to completion. Cancelled and disputed bookings
 * have left the flow, so they show nothing (the status badge says it). */
export function BookingProgress({
  status,
  wasRequested,
}: {
  status: BookingStatus;
  /** Request-to-book bookings start at "requested"; instant bookings skip it. */
  wasRequested: boolean;
}) {
  const t = useTranslations("bookingStatus");
  const at = FLOW.indexOf(status as (typeof FLOW)[number]);
  if (at < 0) return null;
  const steps = FLOW.filter((s) => s !== "requested" || wasRequested);
  return (
    <Timeline
      steps={steps.map((s) => {
        const i = FLOW.indexOf(s);
        return {
          label: t(s),
          state: i < at || status === "completed" ? "done" : i === at ? "current" : "todo",
        };
      })}
    />
  );
}
