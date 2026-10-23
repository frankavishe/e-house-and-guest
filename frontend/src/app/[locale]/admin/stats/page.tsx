import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
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

  return (
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.stats")}</h1>
      <form method="get" className="grid gap-3 sm:grid-cols-4 sm:items-end">
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
        <p className="rounded-xl border border-line p-4 text-muted">{t("errors.generic")}</p>
      ) : (
        <>
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[40rem] text-sm">
              <caption className="sr-only">{t("adminStats.caption")}</caption>
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th scope="col" className="py-2 pr-3 font-medium">
                    {t(`adminStats.group_${groupBy}`)}
                  </th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">
                    {t("adminStats.bookings")}
                  </th>
                  {MONEY.map((m) => (
                    <th key={m} scope="col" className="py-2 pr-3 text-right font-medium">
                      {t(`adminStats.${m}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stats.rows.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-3 text-muted">
                      {t("adminStats.empty")}
                    </td>
                  </tr>
                )}
                {stats.rows.map((row) => (
                  <tr key={row.key} className="border-b border-line">
                    <th scope="row" className="py-2 pr-3 text-left font-normal text-ink">
                      {groupBy === "month" ? monthLabel(row.label) : row.label}
                    </th>
                    <td className="py-2 pr-3 text-right tabular-nums">{row.bookings}</td>
                    {MONEY.map((m) => (
                      <td key={m} className="py-2 pr-3 text-right tabular-nums">
                        {formatTZS(row[m])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold text-ink">
                  <th scope="row" className="py-2 pr-3 text-left">
                    {t("adminStats.total")}
                  </th>
                  <td className="py-2 pr-3 text-right tabular-nums">{stats.totals.bookings}</td>
                  {MONEY.map((m) => (
                    <td key={m} className="py-2 pr-3 text-right tabular-nums">
                      {formatTZS(stats.totals[m])}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="text-xs text-muted">{t("adminStats.definitions")}</p>
          {csv && (
            <div>
              <a href={csv} download className={buttonClasses("secondary")}>
                {t("adminStats.csv")}
              </a>
            </div>
          )}
        </>
      )}
    </>
  );
}
