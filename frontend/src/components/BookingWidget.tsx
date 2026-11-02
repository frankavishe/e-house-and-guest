"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { eatDateString, formatTZS } from "@/lib/format";
import { Button, buttonClasses } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Listing = Schemas["ListingDetail"];
type Quote = Schemas["Quote"];
type Fields = Record<string, string>;

/** Field names shared with the search query (`start_date`, `slot_date`, …), so dates picked
 * in search carry over and a sign-in round trip keeps them. */
const FIELDS = [
  "start_date",
  "end_date",
  "slot_date",
  "slot_start",
  "slot_end",
  "months",
  "quantity",
];
const MONTHS = [1, 2, 3, 6, 9, 12, 18, 24];
const QUOTE_DEBOUNCE_MS = 400;
const NO_AREA: number[] = [];

/** The API period for the mode, or null while it is incomplete. */
function toPeriod(mode: Listing["booking_mode"], f: Fields): Schemas["PeriodParams"] | null {
  switch (mode) {
    case "TIME_SLOT":
      if (!f.slot_date || !f.slot_start || !f.slot_end) return null;
      return {
        start: `${f.slot_date}T${f.slot_start}:00+03:00`,
        end: `${f.slot_date}T${f.slot_end}:00+03:00`,
      };
    case "LEASE":
      if (!f.start_date || !f.months) return null;
      return { start_date: f.start_date, months: Number(f.months) };
    case "QUANTITY":
      if (!f.start_date || !f.end_date) return null;
      return {
        start_date: f.start_date,
        end_date: f.end_date,
        quantity: Math.max(1, Number(f.quantity) || 1),
      };
    default:
      if (!f.start_date || !f.end_date) return null;
      return { start_date: f.start_date, end_date: f.end_date };
  }
}

export function BookingWidget({
  listing,
  signedIn,
  initial,
}: {
  listing: Listing;
  signedIn: boolean;
  initial: Fields;
}) {
  const t = useTranslations();
  const router = useRouter();
  const today = eatDateString(new Date());
  const leaseMonths = MONTHS.filter(
    (n) =>
      (listing.min_duration == null || n >= listing.min_duration) &&
      (listing.max_duration == null || n <= listing.max_duration),
  );
  const [fields, setFields] = useState<Fields>(() => {
    const picked = Object.fromEntries(FIELDS.filter((k) => initial[k]).map((k) => [k, initial[k]]));
    // Leases start on the shortest allowed term, so the form is complete once a date is set.
    if (listing.booking_mode === "LEASE" && !picked.months && leaseMonths.length) {
      picked.months = String(leaseMonths[0]);
    }
    return picked;
  });
  const deliveryRequired = listing.delivery === "required";
  const [delivery, setDelivery] = useState(deliveryRequired);
  const [address, setAddress] = useState("");
  const area = listing.delivery_area ?? NO_AREA;
  const [district, setDistrict] = useState(area.length === 1 ? String(area[0]) : "");
  const [districts, setDistricts] = useState<{ value: string; label: string }[]>([]);
  const [message, setMessage] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [quoting, setQuoting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const idempotencyKey = useRef<string | null>(null);

  const mode = listing.booking_mode;
  const period = useMemo(() => toPeriod(mode, fields), [mode, fields]);
  const wantsDelivery = deliveryRequired || (listing.delivery === "optional" && delivery);
  const needsDistrict = wantsDelivery && signedIn && area.length > 0;
  const slotMinutes = Number(listing.slot_config?.slot_minutes ?? 60) || 60;

  useEffect(() => {
    setQuote(null);
    setQuoteError(null);
    if (!period) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      setQuoting(true);
      try {
        const { data, error: err } = await api.POST("/api/v1/listings/{listing_id}/quote", {
          params: { path: { listing_id: listing.id } },
          body: { ...period, delivery: wantsDelivery },
        });
        if (cancelled) return;
        if (data) setQuote(data);
        else setQuoteError(apiError(err)?.message ?? t("errors.generic"));
      } catch {
        if (!cancelled) setQuoteError(t("errors.network"));
      } finally {
        if (!cancelled) setQuoting(false);
      }
    }, QUOTE_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [listing.id, period, wantsDelivery, t]);

  // The renter picks a district inside the listing's delivery area (OUTSIDE_DELIVERY_AREA).
  useEffect(() => {
    if (!needsDistrict || districts.length) return;
    let cancelled = false;
    api
      .GET("/api/v1/locations", { params: { query: { level: "district" } } })
      .then(({ data }) => {
        if (!cancelled && data) {
          setDistricts(
            data
              .filter((d) => area.includes(d.id))
              .map((d) => ({ value: String(d.id), label: d.name })),
          );
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [needsDistrict, districts.length, area]);

  const set = (key: string) => (e: { target: { value: string } }) =>
    setFields((prev) => ({ ...prev, [key]: e.target.value }));

  const date = (key: string, label: string, min = today) => (
    <Input
      label={label}
      name={key}
      type="date"
      min={min}
      value={fields[key] ?? ""}
      onChange={set(key)}
      required
    />
  );

  const returnTo = () => {
    const qs = new URLSearchParams(
      Object.entries(fields).filter(([, v]) => v) as [string, string][],
    ).toString();
    return `/l/${listing.id}${qs ? `?${qs}` : ""}`;
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!period) return;
    setBusy(true);
    setError(null);
    // One key per attempt; kept after a network failure so a retry replays, not duplicates.
    idempotencyKey.current ??= crypto.randomUUID();
    try {
      const { data, error: err } = await api.POST("/api/v1/bookings", {
        params: { header: { "Idempotency-Key": idempotencyKey.current } },
        body: {
          listing_id: listing.id,
          period,
          delivery: wantsDelivery,
          delivery_district_id: needsDistrict && district ? Number(district) : null,
          delivery_address: wantsDelivery ? address.trim() || null : null,
          message: message.trim() || null,
        },
      });
      idempotencyKey.current = null;
      if (data) {
        router.push(`/book/${data.id}`);
        return;
      }
      setError(apiError(err)?.message ?? t("errors.generic"));
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5"
      aria-labelledby="booking-title"
    >
      <h2 id="booking-title" className="text-lg font-semibold text-ink">
        {t("booking.title")}
      </h2>

      {mode === "TIME_SLOT" ? (
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">{date("slot_date", t("period.date"))}</div>
          <Input
            label={t("period.startTime")}
            name="slot_start"
            type="time"
            step={slotMinutes * 60}
            value={fields.slot_start ?? ""}
            onChange={set("slot_start")}
            required
          />
          <Input
            label={t("period.endTime")}
            name="slot_end"
            type="time"
            step={slotMinutes * 60}
            value={fields.slot_end ?? ""}
            onChange={set("slot_end")}
            required
          />
          <p className="col-span-2 text-sm text-muted">
            {t("booking.slotStep", { minutes: slotMinutes })}
          </p>
        </div>
      ) : mode === "LEASE" ? (
        <div className="grid grid-cols-2 gap-2">
          {date("start_date", t("period.moveIn"))}
          <Select
            label={t("period.months")}
            name="months"
            value={fields.months ?? ""}
            onChange={set("months")}
            required
            options={leaseMonths.map((n) => ({
              value: String(n),
              label: t("period.monthCount", { count: n }),
            }))}
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {listing.default_unit === "night" ? (
            <>
              {date("start_date", t("period.checkIn"))}
              {date("end_date", t("period.checkOut"), fields.start_date || today)}
            </>
          ) : (
            <>
              {date("start_date", t("period.firstDay"))}
              {date("end_date", t("period.lastDay"), fields.start_date || today)}
            </>
          )}
          {mode === "QUANTITY" && (
            <Input
              label={t("period.quantity")}
              name="quantity"
              type="number"
              inputMode="numeric"
              min={1}
              max={listing.stock}
              value={fields.quantity ?? "1"}
              onChange={set("quantity")}
            />
          )}
        </div>
      )}

      {listing.delivery === "optional" && (
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="size-5 accent-brand-600"
            checked={delivery}
            onChange={(e) => setDelivery(e.target.checked)}
          />
          {t("booking.wantDelivery")}
        </label>
      )}
      {needsDistrict && (
        <Select
          label={t("booking.deliveryDistrict")}
          name="delivery_district_id"
          placeholder=""
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
          required
          options={districts}
        />
      )}
      {wantsDelivery && signedIn && (
        <Input
          label={t("booking.deliveryAddress")}
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          maxLength={500}
          required
        />
      )}

      <div aria-live="polite" className="flex flex-col gap-1 text-sm">
        {!period && <p className="text-muted">{t("booking.choosePeriod")}</p>}
        {period && quoting && !quote && <p className="text-muted">{t("booking.quoting")}</p>}
        {quoteError && (
          <p role="alert" className="text-danger">
            {quoteError}
          </p>
        )}
        {quote && <QuoteBreakdown quote={quote} />}
      </div>

      {!listing.instant_book && signedIn && (
        <Input
          label={t("booking.message")}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          maxLength={1000}
        />
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {signedIn ? (
        <Button type="submit" size="lg" full loading={busy} disabled={!quote}>
          {listing.instant_book ? t("booking.bookNow") : t("booking.requestToBook")}
        </Button>
      ) : (
        <Link
          href={`/account/sign-in?returnTo=${encodeURIComponent(returnTo())}`}
          className={buttonClasses("primary", "lg", true)}
        >
          {t("booking.signInToBook")}
        </Link>
      )}
      <p className="text-xs text-muted">
        {listing.instant_book ? t("booking.instantNote") : t("booking.requestNote")}
      </p>
    </form>
  );
}

/** Quote lines, fees, deposit and total (also used on checkout). */
export function QuoteBreakdown({ quote }: { quote: Quote }) {
  const t = useTranslations("booking");
  const units = useTranslations("units");
  const row = (label: string, amount: number, strong = false) => (
    <div key={label} className={`flex justify-between gap-2 ${strong ? "font-semibold" : ""}`}>
      <dt className={strong ? "text-ink" : "text-muted"}>{label}</dt>
      <dd className="tabular-nums text-ink">{formatTZS(amount)}</dd>
    </div>
  );
  return (
    <dl className="flex flex-col gap-1 text-sm">
      {quote.lines.map((l, i) => (
        <div key={i} className="flex justify-between gap-2">
          <dt className="text-muted">
            {l.label === "season" ? `${t("seasonRate")} · ` : ""}
            {t("line", { count: l.count, unit: units(l.unit) })} ({formatTZS(l.unit_price_tzs)})
          </dt>
          <dd className="tabular-nums text-ink">{formatTZS(l.amount_tzs)}</dd>
        </div>
      ))}
      {quote.delivery_fee_tzs > 0 && row(t("deliveryFee"), quote.delivery_fee_tzs)}
      {quote.service_fee_tzs > 0 && row(t("serviceFee"), quote.service_fee_tzs)}
      {quote.deposit_tzs > 0 && row(t("deposit"), quote.deposit_tzs)}
      <div className="border-t border-line pt-1">{row(t("total"), quote.total_tzs, true)}</div>
    </dl>
  );
}
