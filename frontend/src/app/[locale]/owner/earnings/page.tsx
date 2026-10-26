import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { PayoutMethods } from "@/components/PayoutMethods";
import { PayoutStatusBadge } from "@/components/PayoutStatusBadge";
import { buttonClasses } from "@/components/ui/Button";
import { StatCard } from "@/components/ui/StatCard";
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
        ["gross", totals.gross_tzs, "chart"],
        ["paidOut", totals.paid_out_tzs, "checkCircle"],
        ["pending", totals.pending_tzs, "clock"],
      ] as const)
    : [];
  // Net per month of the bookings shown, last six months that have any.
  const monthFmt = new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "sw-TZ", {
    month: "short",
    timeZone: "Africa/Dar_es_Salaam",
  });
  const byMonth = new Map<string, { label: string; value: number }>();
  for (const item of [...items].sort((a, b) => a.period.start.localeCompare(b.period.start))) {
    const key = item.period.start.slice(0, 7);
    const entry = byMonth.get(key) ?? {
      label: monthFmt.format(new Date(item.period.start)),
      value: 0,
    };
    entry.value += item.net_tzs;
    byMonth.set(key, entry);
  }
  const months = [...byMonth.values()].slice(-6);

  return (
    <div className="flex w-full flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("earnings.title")}</h1>
        <form
          className="flex flex-wrap items-end gap-2 rounded-[var(--radius-card)] bg-card p-2 pl-4"
          role="search"
        >
          <Input label={t("earnings.from")} type="date" name="from" defaultValue={from} />
          <Input label={t("earnings.to")} type="date" name="to" defaultValue={to} />
          <button type="submit" className={`${buttonClasses("primary")} mb-1`}>
            {t("earnings.apply")}
          </button>
          {(from || to) && (
            <Link
              href="/owner/earnings"
              className="mb-1 px-2 py-2 text-sm text-brand-700 hover:underline"
            >
              {t("earnings.clear")}
            </Link>
          )}
        </form>
      </div>

      {totals && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <div className="relative overflow-hidden rounded-[var(--radius-card)] bg-hero p-5 text-white sm:col-span-2 xl:col-span-1">
            <p className="text-sm font-medium text-white/85">{t("earnings.net")}</p>
            <div className="mt-3 flex items-end justify-between gap-3">
              <Money amount={totals.net_tzs} className="text-3xl font-semibold tracking-tight" />
              {months.length > 1 && (
                <div aria-hidden className="flex items-end gap-1.5">
                  {months.map((m, i) => (
                    <div key={m.label} className="flex flex-col items-center gap-1">
                      <div className="flex h-12 w-3.5 items-end">
                        <div
                          className={`w-full rounded-full ${i === months.length - 1 ? "bg-white" : "bg-white/40"}`}
                          style={{
                            height: `${Math.max(8, (m.value / Math.max(1, ...months.map((x) => x.value))) * 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-[9px] leading-none text-white/75">{m.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <p className="mt-2 text-xs text-white/75">
              {t("earnings.commission")}: <Money amount={totals.commission_tzs} />
            </p>
          </div>
          {tiles.map(([key, amount, icon]) => (
            <StatCard
              key={key}
              label={t(`earnings.${key}`)}
              icon={icon}
              value={<Money amount={amount} className="text-2xl" />}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr] xl:items-start">
        <section
          aria-labelledby="earning-items"
          className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5"
        >
          <h2 id="earning-items" className="text-lg font-semibold text-ink">
            {t("earnings.bookings")}
          </h2>
          {items.length === 0 ? (
            <p className="rounded-2xl bg-surface p-4 text-muted">{t("earnings.empty")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((item) => (
                <li
                  key={item.booking_id}
                  className="flex flex-col gap-1 rounded-2xl bg-surface p-4"
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

        <div className="flex flex-col gap-4">
          <PayoutMethods methods={methods ?? []} />

          <section
            aria-labelledby="payout-history"
            className="flex flex-col gap-3 rounded-[var(--radius-card)] bg-card p-5"
          >
            <h2 id="payout-history" className="text-lg font-semibold text-ink">
              {t("earnings.payouts")}
            </h2>
            {(payouts?.items.length ?? 0) === 0 ? (
              <p className="rounded-2xl bg-surface p-4 text-muted">{t("earnings.noPayouts")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {payouts?.items.map((p) => (
                  <li key={p.id} className="flex flex-col gap-1 rounded-2xl bg-surface p-4">
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
      </div>
    </div>
  );
}
