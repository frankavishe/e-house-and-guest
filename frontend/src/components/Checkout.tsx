"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { formatPhone, formatTZS } from "@/lib/format";
import { withLocale } from "@/lib/returnTo";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

type Payment = Schemas["PaymentOut"];
type Network = Payment["network"];

const NETWORKS: Network[] = ["mpesa", "mixx", "airtel", "halopesa", "azampesa"];
const POLL_MS = 3000;
const FAILURES = ["insufficient_funds", "declined", "timeout", "cancelled"];

function remaining(dueAt: string | null, now: number): number | null {
  return dueAt ? Math.max(0, Math.floor((new Date(dueAt).getTime() - now) / 1000)) : null;
}

function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Mobile-money checkout: choose network and number, start the payment, then poll it every
 * 3 s until the provider answers. Success goes to the receipt; failure allows a retry. */
export function Checkout({
  bookingId,
  listingId,
  amount,
  installment,
  paymentDueAt,
  defaultPhone,
  pending,
  testMode,
}: {
  bookingId: string;
  listingId: string;
  amount: number;
  installment: { id: string; seq: number } | null;
  paymentDueAt: string | null;
  defaultPhone: string;
  pending: Payment | null;
  testMode: boolean;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const [network, setNetwork] = useState<Network>(pending?.network ?? "mpesa");
  const [msisdn, setMsisdn] = useState(formatPhone(defaultPhone));
  const [payment, setPayment] = useState<Payment | null>(pending);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const left = installment ? null : remaining(paymentDueAt, now);
  const expired = left === 0 && payment?.status !== "pending";
  const waiting = payment?.status === "pending";

  useEffect(() => {
    if (!paymentDueAt || installment) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [paymentDueAt, installment]);

  const settled = useCallback(
    (p: Payment) => {
      setPayment(p);
      if (p.status === "succeeded") {
        // Full navigation so the receipt renders from fresh server data.
        window.location.assign(withLocale(`/book/${bookingId}/receipt`, locale));
      } else if (p.status !== "pending") {
        const reason = FAILURES.includes(p.failure_reason ?? "")
          ? t(`paymentFailure.${p.failure_reason}`)
          : t("paymentFailure.other");
        setError(`${t("checkout.failed", { reason })} ${t("checkout.tryAgain")}`);
      }
    },
    [bookingId, locale, t],
  );

  useEffect(() => {
    if (payment?.status !== "pending") return;
    const id = payment.id;
    const timer = setInterval(async () => {
      try {
        const { data } = await api.GET("/api/v1/payments/{payment_id}", {
          params: { path: { payment_id: id } },
        });
        if (data && data.status !== "pending") settled(data);
      } catch {
        // offline for a moment: keep polling
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [payment?.id, payment?.status, settled]);

  async function pay(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST("/api/v1/bookings/{booking_id}/payments", {
        params: { path: { booking_id: bookingId } },
        body: { network, msisdn, installment_id: installment?.id ?? null },
      });
      if (data) settled(data);
      else setError(apiError(err)?.message ?? t("errors.generic"));
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  if (expired) {
    return (
      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
        <p role="alert" className="text-danger">
          {t("checkout.expired")}
        </p>
        <Link href={`/l/${listingId}`} className="text-brand-700 hover:underline">
          {t("checkout.backToListing")}
        </Link>
      </div>
    );
  }

  return (
    <form
      onSubmit={pay}
      className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4"
    >
      <fieldset className="flex flex-col gap-2" disabled={waiting}>
        <legend className="mb-1 text-sm font-medium text-ink">{t("checkout.network")}</legend>
        <div className="grid grid-cols-2 gap-2">
          {NETWORKS.map((n) => (
            <label
              key={n}
              className={`flex h-12 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm ${
                network === n ? "border-brand-600 bg-brand-50 font-medium" : "border-line"
              }`}
            >
              <input
                type="radio"
                name="network"
                value={n}
                checked={network === n}
                onChange={() => setNetwork(n)}
                className="accent-brand-600"
              />
              {t(`networks.${n}`)}
            </label>
          ))}
        </div>
      </fieldset>

      <Input
        label={t("checkout.phone")}
        hint={t("checkout.phoneHint")}
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        value={msisdn}
        onChange={(e) => setMsisdn(e.target.value)}
        disabled={waiting}
        required
      />
      {testMode && <p className="text-xs text-muted">{t("checkout.testNumbers")}</p>}

      <div aria-live="polite" className="flex flex-col gap-2 text-sm">
        {waiting && (
          <p className="flex items-center gap-2 rounded-lg bg-brand-50 p-3 text-brand-800">
            <span
              aria-hidden
              className="size-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent"
            />
            {t("checkout.waiting")}
          </p>
        )}
        {error && (
          <p role="alert" className="text-danger">
            {error}
          </p>
        )}
        {left != null && left > 0 && (
          <p className="text-muted">{t("checkout.expiresIn", { time: clock(left) })}</p>
        )}
      </div>

      <Button type="submit" size="lg" full loading={busy || waiting}>
        {installment
          ? t("checkout.payInstallment", { seq: installment.seq, amount: formatTZS(amount) })
          : t("checkout.pay", { amount: formatTZS(amount) })}
      </Button>
    </form>
  );
}
