import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { ClaimResolveActions } from "@/components/ClaimResolveActions";
import { Money } from "@/components/Money";
import { Icon } from "@/components/icons";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { PageHeader } from "@/components/ui/PageHeader";
import { Link } from "@/i18n/navigation";
import { getAdminClaims, type AdminClaim, type ClaimStatus } from "@/lib/api/bookings";
import { formatDateTime, formatPhone, formatTZS } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ status?: string }>;
};

const STATUSES: ClaimStatus[] = ["open", "resolved"];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("claims"), robots: { index: false } };
}

/** Damage claims and disputes, oldest first. Resolving decides the held deposit: the award
 * goes to the owner and the rest back to the renter (FR-027, FR-031). */
export default async function AdminClaimsPage({ params, searchParams }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const { status: rawStatus } = await searchParams;
  const status = STATUSES.find((s) => s === rawStatus) ?? "open";
  const [t, page] = await Promise.all([getTranslations(), getAdminClaims(status, 1)]);
  const items = page?.items ?? [];

  const party = (label: string, person: AdminClaim["renter"]) => (
    <div className="flex min-w-0 items-center gap-2 rounded-2xl bg-surface p-3">
      <Avatar name={person.name} size="sm" />
      <div className="min-w-0">
        <p className="text-xs text-muted">{label}</p>
        <p className="truncate font-medium text-ink">
          {person.name} · {formatPhone(person.phone)}
        </p>
      </div>
    </div>
  );

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.claims")} subtitle={t("admin.sub_claims")} />
      <FilterPills
        label={t("adminClaims.filter")}
        pills={STATUSES.map((s) => ({
          href: `/admin/claims?status=${s}`,
          label: t(`claim.status_${s}`),
          current: s === status,
        }))}
      />
      {items.length === 0 ? (
        <EmptyState icon="scale">{t("adminClaims.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((c) => (
            <li key={c.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
                  <Icon name="scale" className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/book/${c.booking_id}`}
                    className="font-semibold text-brand-700 hover:underline"
                  >
                    {c.booking_code}
                  </Link>
                  <p className="truncate text-sm text-muted">
                    {t(`claim.kind_${c.kind}`)} · {t(`claim.openedBy_${c.opened_by}`)}
                  </p>
                </div>
                <BookingStatusBadge status={c.booking_status} />
              </div>
              <blockquote className="whitespace-pre-line rounded-2xl rounded-tl-md bg-surface p-3 text-sm text-ink">
                {c.description}
              </blockquote>
              <InfoTiles
                tiles={[
                  c.amount_claimed_tzs != null && {
                    label: t("adminClaims.claimed"),
                    value: <span className="tabular-nums">{formatTZS(c.amount_claimed_tzs)}</span>,
                  },
                  { label: t("adminClaims.deposit"), value: <Money amount={c.deposit_tzs} /> },
                  { label: t("adminClaims.opened"), value: formatDateTime(c.created_at, locale) },
                  c.resolution && {
                    label: t("adminClaims.resolution"),
                    value: `${t(`claim.resolution_${c.resolution}`)}${
                      c.amount_awarded_tzs
                        ? ` · ${t("claim.awarded", { amount: formatTZS(c.amount_awarded_tzs) })}`
                        : ""
                    }`,
                    wide: true,
                  },
                  c.resolution_note && {
                    label: t("adminClaims.note"),
                    value: c.resolution_note,
                    wide: true,
                  },
                ]}
              />
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                {party(t("checkout.renter"), c.renter)}
                {party(t("checkout.owner"), c.owner)}
              </div>
              {c.evidence.length > 0 && (
                <div className="flex flex-col gap-2">
                  <p className="text-xs font-medium text-muted">{t("adminClaims.evidence")}</p>
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {c.evidence.map((e, i) => (
                      <li key={e.key}>
                        <a
                          href={e.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 font-medium text-brand-700 hover:bg-brand-50"
                        >
                          <Icon name="box" className="size-4" />
                          {t("adminClaims.file", { n: i + 1 })}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {c.status === "open" && <ClaimResolveActions id={c.id} deposit={c.deposit_tzs} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
