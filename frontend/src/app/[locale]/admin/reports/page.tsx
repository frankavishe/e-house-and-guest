import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ReportDecisionActions } from "@/components/ReportDecisionActions";
import { Badge } from "@/components/ui/Badge";
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
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.reports")}</h1>
      <nav
        aria-label={t("adminReports.filter")}
        className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
      >
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`/admin/reports?status=${s}`}
            aria-current={s === status ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
              s === status ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
            }`}
          >
            {t(`adminReports.status_${s}`)}
          </Link>
        ))}
      </nav>
      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("adminReports.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((r) => (
            <li
              key={r.id}
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-ink">
                  {t(`adminReports.kind_${r.target_kind}`)} ·{" "}
                  {r.target_kind === "listing" ? (
                    <Link href={`/l/${r.target_id}`} className="text-brand-700 hover:underline">
                      {r.target_label}
                    </Link>
                  ) : (
                    <Link href={`/u/${r.target_id}`} className="text-brand-700 hover:underline">
                      {r.target_label}
                    </Link>
                  )}
                </span>
                <Badge tone={r.target_status === "suspended" ? "danger" : "neutral"}>
                  {r.target_kind === "listing"
                    ? t(`listingStatus.${r.target_status}`)
                    : t(`adminUsers.status_${r.target_status}`)}
                </Badge>
              </div>
              <p className="whitespace-pre-line text-sm text-ink">{r.reason}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">{t("adminReports.reporter")}</dt>
                <dd>
                  {r.reporter.name} · {formatPhone(r.reporter.phone)}
                </dd>
                <dt className="text-muted">{t("adminReports.reported")}</dt>
                <dd>{formatDateTime(r.created_at, locale)}</dd>
                {r.open_reports_on_target > 1 && (
                  <>
                    <dt className="text-muted">{t("adminReports.openOnTarget")}</dt>
                    <dd>{r.open_reports_on_target}</dd>
                  </>
                )}
                {r.handled_at && (
                  <>
                    <dt className="text-muted">{t("adminReports.handled")}</dt>
                    <dd>{formatDateTime(r.handled_at, locale)}</dd>
                  </>
                )}
              </dl>
              {r.status === "open" && (
                <ReportDecisionActions id={r.id} canSuspend={r.target_status === "active"} />
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
