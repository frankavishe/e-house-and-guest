import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { PayoutActions } from "@/components/PayoutActions";
import { PayoutStatusBadge } from "@/components/PayoutStatusBadge";
import { Link } from "@/i18n/navigation";
import { getAdminPayouts, type PayoutStatus } from "@/lib/api/owner";
import { formatDateTime, formatPhone } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ status?: string }>;
};

const STATUSES: PayoutStatus[] = ["pending", "processing", "failed", "paid"];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("payouts"), robots: { index: false } };
}

/** Payouts by status, oldest first. With manual payouts, `pending` is the to-send queue:
 * send the money, then mark it paid with the transfer reference (R7). */
export default async function AdminPayoutsPage({ params, searchParams }: Props) {
  const { locale: raw } = await params;
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const { status: rawStatus } = await searchParams;
  const status = STATUSES.find((s) => s === rawStatus) ?? "pending";
  const [t, page] = await Promise.all([getTranslations(), getAdminPayouts(status, 1)]);
  const items = page?.items ?? [];

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{t("admin.payouts")}</h1>
      <nav
        aria-label={t("adminPayouts.filter")}
        className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
      >
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={`/admin/payouts?status=${s}`}
            aria-current={s === status ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
              s === status ? "bg-brand-600 text-white" : "bg-card text-ink hover:bg-brand-50"
            }`}
          >
            {t(`payoutStatus.${s}`)}
          </Link>
        ))}
      </nav>
      {items.length === 0 ? (
        <p className="rounded-3xl bg-card p-4 text-muted">{t("adminPayouts.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((p) => (
            <li
              key={p.id}
              className="flex flex-col gap-3 rounded-3xl bg-card p-4"
            >
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-ink">{p.owner.display_name}</p>
                  <PayoutStatusBadge status={p.status} />
                </div>
                <Money amount={p.amount_tzs} className="text-lg font-semibold text-ink" />
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  <dt className="text-muted">{t("adminPayouts.owner")}</dt>
                  <dd>{formatPhone(p.owner.phone)}</dd>
                  <dt className="text-muted">{t("adminPayouts.destination")}</dt>
                  <dd>
                    {p.destination
                      ? [
                          p.destination.network
                            ? t(`networks.${p.destination.network}`)
                            : p.destination.bank_name,
                          p.destination.msisdn
                            ? formatPhone(p.destination.msisdn)
                            : p.destination.account_number_masked,
                          p.destination.account_name,
                        ]
                          .filter(Boolean)
                          .join(" · ")
                      : t("adminPayouts.noDestination")}
                  </dd>
                  <dt className="text-muted">{t("adminPayouts.created")}</dt>
                  <dd>{formatDateTime(p.created_at, locale)}</dd>
                  {p.provider_ref && (
                    <>
                      <dt className="text-muted">{t("adminPayouts.reference")}</dt>
                      <dd className="font-mono">{p.provider_ref}</dd>
                    </>
                  )}
                  {p.failure_reason && (
                    <>
                      <dt className="text-muted">{t("adminPayouts.failure")}</dt>
                      <dd className="text-danger">{p.failure_reason}</dd>
                    </>
                  )}
                  <dt className="text-muted">{t("adminPayouts.bookings")}</dt>
                  <dd>{p.items.map((i) => i.booking_code).join(", ")}</dd>
                </dl>
              </div>
              <PayoutActions id={p.id} status={p.status} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
