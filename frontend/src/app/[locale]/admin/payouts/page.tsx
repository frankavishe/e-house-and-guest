import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Money } from "@/components/Money";
import { PayoutActions } from "@/components/PayoutActions";
import { PayoutStatusBadge } from "@/components/PayoutStatusBadge";
import { Icon } from "@/components/icons";
import { Avatar } from "@/components/ui/Avatar";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.payouts")} subtitle={t("admin.sub_payouts")} />
      <FilterPills
        label={t("adminPayouts.filter")}
        pills={STATUSES.map((s) => ({
          href: `/admin/payouts?status=${s}`,
          label: t(`payoutStatus.${s}`),
          current: s === status,
        }))}
      />
      {items.length === 0 ? (
        <EmptyState icon="wallet">{t("adminPayouts.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((p) => (
            <li key={p.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-center gap-3">
                <Avatar name={p.owner.display_name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink">{p.owner.display_name}</p>
                  <p className="truncate text-sm text-muted">{formatPhone(p.owner.phone)}</p>
                </div>
                <PayoutStatusBadge status={p.status} />
              </div>
              <div className="flex items-center gap-3 rounded-2xl bg-surface p-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
                  <Icon name="wallet" className="size-5" />
                </span>
                <div className="min-w-0">
                  <Money
                    amount={p.amount_tzs}
                    className="text-2xl font-semibold tracking-tight text-ink"
                  />
                  <p className="truncate text-sm text-muted">
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
                  </p>
                </div>
              </div>
              <InfoTiles
                tiles={[
                  { label: t("adminPayouts.created"), value: formatDateTime(p.created_at, locale) },
                  p.provider_ref && {
                    label: t("adminPayouts.reference"),
                    value: p.provider_ref,
                    mono: true,
                  },
                  {
                    label: t("adminPayouts.bookings"),
                    value: p.items.map((i) => i.booking_code).join(", "),
                  },
                  p.failure_reason && {
                    label: t("adminPayouts.failure"),
                    value: <span className="text-danger">{p.failure_reason}</span>,
                    wide: true,
                  },
                ]}
              />
              <PayoutActions id={p.id} status={p.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
