"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";

/** One rating (1–5) and optional comment per party after a completed booking (FR-029). */
export function ReviewForm({
  bookingId,
  about,
}: {
  bookingId: string;
  about: "listing" | "renter";
}) {
  const t = useTranslations("reviews");
  const tErr = useTranslations("errors");
  const router = useRouter();
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!rating) return;
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/bookings/{booking_id}/reviews", {
        params: { path: { booking_id: bookingId } },
        body: { rating, body: body.trim() || null },
      });
      if (err) setError(apiError(err)?.message ?? tErr("generic"));
      else router.refresh();
    } catch {
      setError(tErr("network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <p className="text-sm text-muted">
        {t(about === "listing" ? "promptListing" : "promptRenter")}
      </p>
      <fieldset className="flex gap-1">
        <legend className="sr-only">{t("rating")}</legend>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n} className="cursor-pointer">
            <input
              type="radio"
              name="rating"
              value={n}
              checked={rating === n}
              onChange={() => setRating(n)}
              className="sr-only"
            />
            <span
              aria-label={t("stars", { count: n })}
              className={`text-3xl leading-none ${n <= rating ? "text-amber-500" : "text-line"}`}
            >
              ★
            </span>
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("comment")}</span>
        <textarea
          rows={3}
          maxLength={1000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="rounded-2xl border border-line bg-surface p-3 text-sm text-ink"
        />
      </label>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div>
        <Button type="submit" loading={busy} disabled={!rating}>
          {t("submit")}
        </Button>
      </div>
    </form>
  );
}
