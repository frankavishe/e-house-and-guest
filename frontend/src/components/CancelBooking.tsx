"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { formatDateTime, formatTZS } from "@/lib/format";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

type Preview = Schemas["CancelPreviewOut"];

/** Cancel a booking (FR-026): first shows what the policy refunds now, then confirms. */
export function CancelBooking({ bookingId }: { bookingId: string }) {
  const t = useTranslations();
  const locale = useLocale() === "en" ? "en" : "sw";
  const router = useRouter();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const path = { params: { path: { booking_id: bookingId } } };

  async function run<T>(call: () => Promise<{ data?: T; error?: unknown }>): Promise<T | null> {
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await call();
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      return data ?? null;
    } catch {
      setError(t("errors.network"));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function open() {
    const data = await run(() => api.GET("/api/v1/bookings/{booking_id}/cancel-preview", path));
    if (data) setPreview(data);
  }

  async function confirm() {
    const done = await run(() =>
      api.POST("/api/v1/bookings/{booking_id}/cancel", {
        ...path,
        body: { reason: reason.trim() || null },
      }),
    );
    if (done) {
      setPreview(null);
      router.refresh();
    }
  }

  const rows: [string, number][] = preview
    ? [
        [t("cancel.rental", { percent: preview.percent }), preview.rental_refund_tzs],
        [t("booking.deliveryFee"), preview.delivery_refund_tzs],
        [t("booking.serviceFee"), preview.service_fee_refund_tzs],
        [t("booking.deposit"), preview.deposit_refund_tzs],
      ]
    : [];

  return (
    <div className="flex flex-col gap-3">
      {preview ? (
        <>
          {preview.cancelled_by === "owner" && (
            <p className="rounded-2xl bg-warning-soft p-3 text-sm text-warning">
              {t("cancel.ownerWarning")}
            </p>
          )}
          {preview.paid_tzs === 0 ? (
            <p className="text-sm text-ink">{t("cancel.nothingPaid")}</p>
          ) : (
            <dl className="flex flex-col gap-1 text-sm">
              {rows
                .filter(([, amount]) => amount > 0)
                .map(([label, amount]) => (
                  <div key={label} className="flex justify-between gap-2">
                    <dt className="text-muted">{label}</dt>
                    <dd className="tabular-nums text-ink">{formatTZS(amount)}</dd>
                  </div>
                ))}
              <div className="flex justify-between gap-2 border-t border-line pt-1 font-semibold">
                <dt>
                  {preview.cancelled_by === "renter" ? t("cancel.youGet") : t("cancel.renterGets")}
                </dt>
                <dd className="tabular-nums">{formatTZS(preview.refund_tzs)}</dd>
              </div>
            </dl>
          )}
          {preview.deadline && (
            <p className="text-sm text-muted">
              {t("cancel.deadline", { time: formatDateTime(preview.deadline, locale) })}
            </p>
          )}
          <Input
            label={t("cancel.reason")}
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" loading={busy} onClick={confirm}>
              {t("cancel.confirm")}
            </Button>
            <Button variant="secondary" onClick={() => setPreview(null)}>
              {t("cancel.keep")}
            </Button>
          </div>
        </>
      ) : (
        <div>
          <Button variant="secondary" loading={busy} onClick={open}>
            {t("cancel.open")}
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
