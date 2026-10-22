import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { Money } from "@/components/Money";
import { Pagination } from "@/components/Pagination";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
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
    <>
      <h1 className="text-xl font-bold text-ink">{t("admin.bookings")}</h1>
      <form method="get" className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
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
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="attention" value="true" defaultChecked={attention} />
          {t("adminBookings.attentionOnly")}
        </label>
        <Button type="submit">{t("adminBookings.find")}</Button>
      </form>
      {items.length === 0 ? (
        <p className="rounded-xl border border-line p-4 text-muted">{t("adminBookings.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((b) => (
            <li
              key={b.id}
              className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link href={`/book/${b.id}`} className="font-medium text-brand-700 hover:underline">
                  {b.code}
                </Link>
                <span className="flex flex-wrap gap-1">
                  {b.attention && <Badge tone="danger">{t("adminBookings.attention")}</Badge>}
                  {b.open_claim && <Badge tone="warning">{t("adminBookings.openClaim")}</Badge>}
                  <BookingStatusBadge status={b.status} />
                </span>
              </div>
              <p className="text-sm text-ink">{b.listing_title}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">{t("adminBookings.dates")}</dt>
                <dd>
                  {formatDate(b.period.start, locale)} – {formatDate(b.period.end, locale)}
                </dd>
                <dt className="text-muted">{t("checkout.renter")}</dt>
                <dd>
                  {b.renter.name} · {formatPhone(b.renter.phone)}
                </dd>
                <dt className="text-muted">{t("checkout.owner")}</dt>
                <dd>
                  {b.owner.name} · {formatPhone(b.owner.phone)}
                </dd>
                <dt className="text-muted">{t("adminBookings.total")}</dt>
                <dd>
                  <Money amount={b.total_tzs} />
                </dd>
              </dl>
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
    </>
  );
}
