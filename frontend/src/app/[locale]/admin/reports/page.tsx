import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ReportDecisionActions } from "@/components/ReportDecisionActions";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { PageHeader } from "@/components/ui/PageHeader";
import { Link } from "@/i18n/navigation";
import { getAbuseReports, type ReportStatus } from "@/lib/api/admin";
import { formatDateTime, formatPhone } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ status?: string }>;
};

const STATUSES: ReportStatus[] = ["open", "actioned", "dismissed"];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("reports"), robots: { index: false } };
}

/** Abuse reports on listings and users (FR-030): open ones oldest first. */
export default async function AdminReportsPage({ params, searchParams }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const { status: rawStatus } = await searchParams;
  const status = STATUSES.find((s) => s === rawStatus) ?? "open";
  const [t, page] = await Promise.all([getTranslations(), getAbuseReports(status, 1)]);
  const items = page?.items ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.reports")} subtitle={t("admin.sub_reports")} />
      <FilterPills
        label={t("adminReports.filter")}
        pills={STATUSES.map((s) => ({
          href: `/admin/reports?status=${s}`,
          label: t(`adminReports.status_${s}`),
          current: s === status,
        }))}
      />
      {items.length === 0 ? (
        <EmptyState icon="flag">{t("adminReports.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((r) => (
            <li key={r.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
                  <Icon name={r.target_kind === "listing" ? "grid" : "user"} className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={r.target_kind === "listing" ? `/l/${r.target_id}` : `/u/${r.target_id}`}
                    className="block truncate font-semibold text-brand-700 hover:underline"
                  >
                    {r.target_label}
                  </Link>
                  <p className="text-sm text-muted">{t(`adminReports.kind_${r.target_kind}`)}</p>
                </div>
                <Badge tone={r.target_status === "suspended" ? "danger" : "neutral"}>
                  {r.target_kind === "listing"
                    ? t(`listingStatus.${r.target_status}`)
                    : t(`adminUsers.status_${r.target_status}`)}
                </Badge>
              </div>
              <blockquote className="whitespace-pre-line rounded-2xl rounded-tl-md bg-surface p-3 text-sm text-ink">
                {r.reason}
              </blockquote>
              <InfoTiles
                tiles={[
                  {
                    label: t("adminReports.reporter"),
                    value: `${r.reporter.name} · ${formatPhone(r.reporter.phone)}`,
                  },
                  {
                    label: t("adminReports.reported"),
                    value: formatDateTime(r.created_at, locale),
                  },
                  r.open_reports_on_target > 1 && {
                    label: t("adminReports.openOnTarget"),
                    value: <span className="text-warning">{r.open_reports_on_target}</span>,
                  },
                  r.handled_at && {
                    label: t("adminReports.handled"),
                    value: formatDateTime(r.handled_at, locale),
                  },
                ]}
              />
              {r.status === "open" && (
                <ReportDecisionActions id={r.id} canSuspend={r.target_status === "active"} />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
