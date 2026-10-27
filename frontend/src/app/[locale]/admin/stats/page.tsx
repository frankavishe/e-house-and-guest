import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { StatCard } from "@/components/ui/StatCard";
import { getStats, type StatsGroup } from "@/lib/api/admin";
import { formatTZS } from "@/lib/format";
import { cleanParams, getParam, type RawParams } from "@/lib/search";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<RawParams> };

const GROUPS: StatsGroup[] = ["month", "category", "region"];
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const MONEY = ["gbv_tzs", "commission_tzs", "refunds_tzs", "payouts_tzs"] as const;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("stats"), robots: { index: false } };
}

/** Bookings, gross booking value, commission, refunds and payouts by month, category or
 * region, read from the ledger (FR-032), with a CSV download of the same table. */
export default async function AdminStatsPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const pairs = cleanParams(query);
  const from = getParam(pairs, "from");
  const to = getParam(pairs, "to");
  const groupBy = GROUPS.find((g) => g === getParam(pairs, "group_by")) ?? "month";
  const monthFormat = new Intl.DateTimeFormat(raw === "en" ? "en-GB" : "sw-TZ", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const shortMonth = new Intl.DateTimeFormat(raw === "en" ? "en-GB" : "sw-TZ", {
    month: "short",
    timeZone: "UTC",
  });
  const monthLabel = (label: string) =>
    /^\d{4}-\d{2}$/.test(label) ? monthFormat.format(new Date(`${label}-01T12:00:00Z`)) : label;
  const [t, stats] = await Promise.all([
    getTranslations(),
    getStats(
      from && DATE.test(from) ? from : undefined,
      to && DATE.test(to) ? to : undefined,
      groupBy,
    ),
  ]);
  const csv = stats
    ? `/api/v1/admin/stats?${new URLSearchParams({
        from: stats.from,
        to: stats.to,
        group_by: groupBy,
        format: "csv",
      })}`
    : null;

  const months =
    stats && groupBy === "month"
      ? stats.rows.slice(-6).map((row) => ({
          label: shortMonth.format(new Date(`${row.label}-01T12:00:00Z`)),
          value: row.gbv_tzs,
        }))
      : [];
  const tiles = stats
    ? ([
        ["commission_tzs", "wallet"],
        ["refunds_tzs", "scale"],
        ["payouts_tzs", "checkCircle"],
      ] as const)
    : [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title={t("admin.stats")}
        subtitle={t("admin.sub_stats")}
        actions={
          csv && (
            <a href={csv} download className={buttonClasses("secondary")}>
              {t("adminStats.csv")}
            </a>
          )
        }
      />
      <form
        method="get"
        className="grid gap-3 rounded-[var(--radius-card)] bg-card p-4 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end"
      >
        <Input label={t("adminStats.from")} type="date" name="from" defaultValue={stats?.from} />
        <Input label={t("adminStats.to")} type="date" name="to" defaultValue={stats?.to} />
        <Select
          label={t("adminStats.groupBy")}
          name="group_by"
          defaultValue={groupBy}
          options={GROUPS.map((g) => ({ value: g, label: t(`adminStats.group_${g}`) }))}
        />
        <Button type="submit">{t("adminStats.show")}</Button>
      </form>
      {!stats ? (
        <EmptyState icon="alert">{t("errors.generic")}</EmptyState>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="relative overflow-hidden rounded-[var(--radius-card)] bg-hero p-5 text-white">
              <p className="text-sm font-medium text-white/85">{t("adminStats.gbv_tzs")}</p>
              <div className="mt-3 flex items-end justify-between gap-3">
                <p className="truncate text-3xl font-semibold tabular-nums tracking-tight">
                  {formatTZS(stats.totals.gbv_tzs)}
                </p>
                {months.length > 1 && (
                  <div aria-hidden className="flex items-end gap-1.5">
                    {months.map((m, i) => (
                      <div key={`${m.label}${i}`} className="flex flex-col items-center gap-1">
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
                {t("adminStats.bookings")}: {stats.totals.bookings}
              </p>
            </div>
            {tiles.map(([key, icon]) => (
              <StatCard
                key={key}
                label={t(`adminStats.${key}`)}
                icon={icon}
                value={<span className="text-2xl">{formatTZS(stats.totals[key])}</span>}
              />
            ))}
          </div>

          <section className="rounded-[var(--radius-card)] bg-card p-5">
            <div className="-mx-5 overflow-x-auto px-5">
              <table className="w-full min-w-[40rem] text-sm">
                <caption className="sr-only">{t("adminStats.caption")}</caption>
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-muted">
                    <th scope="col" className="pb-3 pr-3 font-medium">
                      {t(`adminStats.group_${groupBy}`)}
                    </th>
                    <th scope="col" className="pb-3 pr-3 text-right font-medium">
                      {t("adminStats.bookings")}
                    </th>
                    {MONEY.map((m) => (
                      <th key={m} scope="col" className="pb-3 pr-3 text-right font-medium">
                        {t(`adminStats.${m}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stats.rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-muted">
                        {t("adminStats.empty")}
                      </td>
                    </tr>
                  )}
                  {stats.rows.map((row) => (
                    <tr key={row.key} className="border-t border-line">
                      <th scope="row" className="py-3 pr-3 text-left font-medium text-ink">
                        {groupBy === "month" ? monthLabel(row.label) : row.label}
                      </th>
                      <td className="py-3 pr-3 text-right tabular-nums">{row.bookings}</td>
                      {MONEY.map((m) => (
                        <td key={m} className="py-3 pr-3 text-right tabular-nums">
                          {formatTZS(row[m])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-surface font-semibold text-ink">
                    <th scope="row" className="rounded-l-2xl px-3 py-3 text-left">
                      {t("adminStats.total")}
                    </th>
                    <td className="py-3 pr-3 text-right tabular-nums">{stats.totals.bookings}</td>
                    {MONEY.map((m, i) => (
                      <td
                        key={m}
                        className={`py-3 pr-3 text-right tabular-nums ${i === MONEY.length - 1 ? "rounded-r-2xl" : ""}`}
                      >
                        {formatTZS(stats.totals[m])}
                      </td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
            <p className="mt-4 text-xs text-muted">{t("adminStats.definitions")}</p>
          </section>
        </>
      )}
    </div>
  );
}
