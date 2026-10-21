import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { ClaimResolveActions } from "@/components/ClaimResolveActions";
import { Money } from "@/components/Money";
import { Link } from "@/i18n/navigation";
import { getAdminClaims, type ClaimStatus } from "@/lib/api/bookings";
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

  return (
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.claims")}</h1>
      <nav
        aria-label={t("adminClaims.filter")}
        className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
      >
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`/admin/claims?status=${s}`}
            aria-current={s === status ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
              s === status ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
            }`}
          >
            {t(`claim.status_${s}`)}
          </Link>
        ))}
      </nav>
      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("adminClaims.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => (
            <li
              key={c.id}
              className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link
                  href={`/book/${c.booking_id}`}
                  className="font-medium text-brand-700 hover:underline"
                >
                  {c.booking_code}
                </Link>
                <BookingStatusBadge status={c.booking_status} />
              </div>
              <p className="text-sm font-medium text-ink">
                {t(`claim.kind_${c.kind}`)} · {t(`claim.openedBy_${c.opened_by}`)}
              </p>
              <p className="whitespace-pre-line text-sm text-ink">{c.description}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">{t("adminClaims.opened")}</dt>
                <dd>{formatDateTime(c.created_at, locale)}</dd>
                {c.amount_claimed_tzs != null && (
                  <>
                    <dt className="text-muted">{t("adminClaims.claimed")}</dt>
                    <dd className="tabular-nums">{formatTZS(c.amount_claimed_tzs)}</dd>
                  </>
                )}
                <dt className="text-muted">{t("adminClaims.deposit")}</dt>
                <dd>
                  <Money amount={c.deposit_tzs} />
                </dd>
                <dt className="text-muted">{t("checkout.renter")}</dt>
                <dd>
                  {c.renter.name} · {formatPhone(c.renter.phone)}
                </dd>
                <dt className="text-muted">{t("checkout.owner")}</dt>
                <dd>
                  {c.owner.name} · {formatPhone(c.owner.phone)}
                </dd>
                {c.evidence.length > 0 && (
                  <>
                    <dt className="text-muted">{t("adminClaims.evidence")}</dt>
                    <dd className="flex flex-wrap gap-x-3">
                      {c.evidence.map((e, i) => (
                        <a
                          key={e.key}
                          href={e.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-brand-700 hover:underline"
                        >
                          {t("adminClaims.file", { n: i + 1 })}
                        </a>
                      ))}
                    </dd>
                  </>
                )}
                {c.resolution && (
                  <>
                    <dt className="text-muted">{t("adminClaims.resolution")}</dt>
                    <dd>
                      {t(`claim.resolution_${c.resolution}`)}
                      {c.amount_awarded_tzs
                        ? ` · ${t("claim.awarded", { amount: formatTZS(c.amount_awarded_tzs) })}`
                        : ""}
                    </dd>
                  </>
                )}
                {c.resolution_note && (
                  <>
                    <dt className="text-muted">{t("adminClaims.note")}</dt>
                    <dd>{c.resolution_note}</dd>
                  </>
                )}
              </dl>
              {c.status === "open" && <ClaimResolveActions id={c.id} deposit={c.deposit_tzs} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
