"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Accept or decline a booking request (FR-018); the renter is notified either way. */
export function RequestActions({ bookingId }: { bookingId: string }) {
  const t = useTranslations();
  const router = useRouter();
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const path = { booking_id: bookingId };

  async function run(call: () => Promise<{ error?: unknown }>) {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await call();
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {declining ? (
        <>
          <Input label={t("requests.reason")} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button
              variant="danger"
              loading={busy}
              onClick={() =>
                run(() =>
                  api.POST("/api/v1/bookings/{booking_id}/decline", {
                    params: { path },
                    body: { reason: reason.trim() || null },
                  }),
                )
              }
            >
              {t("requests.confirmDecline")}
            </Button>
            <Button variant="secondary" onClick={() => setDeclining(false)}>
              {t("common.back")}
            </Button>
          </div>
        </>
      ) : (
        <div className="flex gap-2">
          <Button
            loading={busy}
            onClick={() => run(() => api.POST("/api/v1/bookings/{booking_id}/accept", { params: { path } }))}
          >
            {t("requests.accept")}
          </Button>
          <Button variant="secondary" onClick={() => setDeclining(true)}>
            {t("requests.decline")}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
