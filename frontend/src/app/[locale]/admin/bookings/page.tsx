import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { Money } from "@/components/Money";
import { Pagination } from "@/components/Pagination";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { InfoTiles } from "@/components/ui/InfoTiles";
import { Input } from "@/components/ui/Input";
import { PageHeader } from "@/components/ui/PageHeader";
import { Select } from "@/components/ui/Select";
import { Link } from "@/i18n/navigation";
import { getAdminBookings, type AdminBooking } from "@/lib/api/admin";
import { formatDate, formatPhone } from "@/lib/format";
import { cleanParams, getParam, type RawParams } from "@/lib/search";

type Props = { params: Promise<{ locale: string }>; searchParams: Promise<RawParams> };

const STATUSES: AdminBooking["status"][] = [
  "requested",
  "awaiting_payment",
  "confirmed",
  "in_progress",
  "completed",
  "cancelled",
  "disputed",
];

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("bookings"), robots: { index: false } };
}

/** Find a booking by code or phone; cancel, refund or follow up from its page (FR-031).
 * "Needs attention" lists future bookings whose listing or a party is suspended. */
export default async function AdminBookingsPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const pairs = cleanParams(query);
  const q = getParam(pairs, "q");
  const status = STATUSES.find((s) => s === getParam(pairs, "status"));
  const attention = getParam(pairs, "attention") === "true";
  const page = Math.max(1, Number(getParam(pairs, "page")) || 1);
  const [t, data] = await Promise.all([
    getTranslations(),
    getAdminBookings({ status, q, attention, page }),
  ]);
  const items = data?.items ?? [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("admin.bookings")} subtitle={t("admin.sub_bookings")} />
      <form
        method="get"
        role="search"
        className="grid gap-3 rounded-[var(--radius-card)] bg-card p-4 sm:grid-cols-[1fr_auto] sm:items-end lg:grid-cols-[1fr_auto_auto_auto]"
      >
        <Input label={t("adminBookings.search")} name="q" defaultValue={q ?? ""} maxLength={50} />
        <Select
          label={t("adminBookings.status")}
          name="status"
          defaultValue={status ?? ""}
          options={[
            { value: "", label: t("adminBookings.all") },
            ...STATUSES.map((s) => ({ value: s, label: t(`bookingStatus.${s}`) })),
          ]}
        />
        <label className="flex items-center gap-2 rounded-full bg-surface px-4 py-2.5 text-sm font-medium">
          <input
            type="checkbox"
            name="attention"
            value="true"
            defaultChecked={attention}
            className="size-4 accent-brand-600"
          />
          {t("adminBookings.attentionOnly")}
        </label>
        <Button type="submit">{t("adminBookings.find")}</Button>
      </form>
      {items.length === 0 ? (
        <EmptyState icon="calendar">{t("adminBookings.empty")}</EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((b) => (
            <li key={b.id} className="flex flex-col gap-4 rounded-[var(--radius-card)] bg-card p-5">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-ink text-surface">
                  <Icon name="calendar" className="size-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/book/${b.id}`}
                    className="font-semibold text-brand-700 hover:underline"
                  >
                    {b.code}
                  </Link>
                  <p className="truncate text-sm text-muted">{b.listing_title}</p>
                </div>
                <Money amount={b.total_tzs} className="shrink-0 font-semibold text-ink" />
              </div>
              <div className="flex flex-wrap gap-1">
                <BookingStatusBadge status={b.status} />
                {b.attention && <Badge tone="danger">{t("adminBookings.attention")}</Badge>}
                {b.open_claim && <Badge tone="warning">{t("adminBookings.openClaim")}</Badge>}
              </div>
              <InfoTiles
                tiles={[
                  {
                    label: t("adminBookings.dates"),
                    value: `${formatDate(b.period.start, locale)} – ${formatDate(b.period.end, locale)}`,
                    wide: true,
                  },
                  {
                    label: t("checkout.renter"),
                    value: `${b.renter.name} · ${formatPhone(b.renter.phone)}`,
                  },
                  {
                    label: t("checkout.owner"),
                    value: `${b.owner.name} · ${formatPhone(b.owner.phone)}`,
                  },
                ]}
              />
            </li>
          ))}
        </ul>
      )}
      {data && (
        <Pagination
          pairs={pairs}
          page={page}
          pageSize={data.page_size}
          total={data.total}
          path="/admin/bookings"
        />
      )}
    </div>
  );
}
