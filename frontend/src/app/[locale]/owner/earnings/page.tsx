import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { PayoutMethods } from "@/components/PayoutMethods";
import { PayoutStatusBadge } from "@/components/PayoutStatusBadge";
import { buttonClasses } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Link, redirect } from "@/i18n/navigation";
import { getEarnings, getOwnerPayouts, getPayoutMethods } from "@/lib/api/owner";
import { getCurrentUser } from "@/lib/api/server";
import { formatDate, formatDateTime, formatPhone } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ from?: string; to?: string }>;
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "earnings" });
  return { title: t("title"), robots: { index: false } };
}

/** Gross, commission and net per booking, payout methods and payout history (US4). */
export default async function OwnerEarningsPage({ params, searchParams }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user?.owner_profile) {
    redirect({
      href: user ? "/owner/onboarding" : "/account/sign-in?returnTo=/owner/earnings",
      locale,
    });
    return null;
  }
  const query = await searchParams;
  const from = query.from && DAY.test(query.from) ? query.from : undefined;
  const to = query.to && DAY.test(query.to) ? query.to : undefined;
  const [t, earnings, payouts, methods] = await Promise.all([
    getTranslations(),
    getEarnings(from, to),
    getOwnerPayouts(1),
    getPayoutMethods(),
  ]);
  const totals = earnings?.totals;
  const items = earnings?.items ?? [];
  const tiles = totals
    ? ([
        ["gross", totals.gross_tzs],
        ["commission", totals.commission_tzs],
        ["net", totals.net_tzs],
        ["paidOut", totals.paid_out_tzs],
        ["pending", totals.pending_tzs],
      ] as const)
    : [];

  return (
    <div className="flex w-full flex-col gap-5">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("earnings.title")}</h1>

      <form className="flex flex-wrap items-end gap-2" role="search">
        <Input label={t("earnings.from")} type="date" name="from" defaultValue={from} />
        <Input label={t("earnings.to")} type="date" name="to" defaultValue={to} />
        <button type="submit" className={buttonClasses("secondary")}>
          {t("earnings.apply")}
        </button>
        {(from || to) && (
          <Link href="/owner/earnings" className="py-2 text-sm text-brand-700 hover:underline">
            {t("earnings.clear")}
          </Link>
        )}
      </form>

      {totals && (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {tiles.map(([key, amount]) => (
            <div
              key={key}
              className={`rounded-3xl bg-card p-3 ${key === "net" ? "col-span-2 sm:col-span-1" : ""}`}
            >
              <dt className="text-xs text-muted">{t(`earnings.${key}`)}</dt>
              <dd>
                <Money amount={amount} className="text-lg font-semibold text-ink" />
              </dd>
            </div>
          ))}
        </dl>
      )}

      <section aria-labelledby="earning-items" className="flex flex-col gap-3">
        <h2 id="earning-items" className="text-lg font-semibold text-ink">
          {t("earnings.bookings")}
        </h2>
        {items.length === 0 ? (
          <p className="rounded-3xl bg-card p-4 text-muted">{t("earnings.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {items.map((item) => (
              <li
                key={item.booking_id}
                className="flex flex-col gap-1 rounded-3xl bg-card p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <Link
                    href={`/book/${item.booking_id}`}
                    className="min-w-0 truncate font-medium text-brand-700 hover:underline"
                  >
                    {item.listing_title}
                  </Link>
                  <PayoutStatusBadge status={item.status} />
                </div>
                <p className="text-sm text-muted">
                  {item.booking_code} · {formatDate(item.period.start, locale)}
                </p>
                <dl className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <dt className="text-xs text-muted">{t("earnings.gross")}</dt>
                    <dd>
                      <Money amount={item.gross_tzs} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{t("earnings.commission")}</dt>
                    <dd>
                      <Money amount={item.commission_tzs} />
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">{t("earnings.net")}</dt>
                    <dd>
                      <Money amount={item.net_tzs} className="font-semibold text-ink" />
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted">{t("earnings.schedule")}</p>
      </section>

      <PayoutMethods methods={methods ?? []} />

      <section aria-labelledby="payout-history" className="flex flex-col gap-3">
        <h2 id="payout-history" className="text-lg font-semibold text-ink">
          {t("earnings.payouts")}
        </h2>
        {(payouts?.items.length ?? 0) === 0 ? (
          <p className="rounded-3xl bg-card p-4 text-muted">{t("earnings.noPayouts")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {payouts?.items.map((p) => (
              <li
                key={p.id}
                className="flex flex-col gap-1 rounded-3xl bg-card p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <Money amount={p.amount_tzs} className="font-semibold text-ink" />
                  <PayoutStatusBadge status={p.status} />
                </div>
                <p className="text-sm text-muted">
                  {formatDateTime(p.paid_at ?? p.created_at, locale)}
                  {p.destination &&
                    ` · ${
                      p.destination.msisdn
                        ? formatPhone(p.destination.msisdn)
                        : (p.destination.account_number_masked ?? p.destination.bank_name)
                    }`}
                </p>
                {p.provider_ref && (
                  <p className="text-sm text-ink">
                    {t("earnings.reference", { ref: p.provider_ref })}
                  </p>
                )}
                {p.status === "failed" && (
                  <p className="text-sm text-danger">
                    {t(
                      p.failure_reason === "no_payout_method"
                        ? "earnings.failedNoMethod"
                        : "earnings.failed",
                    )}
                  </p>
                )}
                <p className="text-xs text-muted">
                  {p.items.map((i) => i.booking_code).join(", ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
