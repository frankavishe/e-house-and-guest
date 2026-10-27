import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { Money } from "@/components/Money";
import { Pagination } from "@/components/Pagination";
import { Icon } from "@/components/icons";
import { buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPills } from "@/components/ui/FilterPills";
import { PageHeader } from "@/components/ui/PageHeader";
import { Link, redirect } from "@/i18n/navigation";
import { listBookings } from "@/lib/api/bookings";
import { getCurrentUser } from "@/lib/api/server";
import { formatPeriod } from "@/lib/format";
import type { Pair } from "@/lib/search";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ role?: string; page?: string }>;
};

const PAGE_SIZE = 20;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "myBookings" });
  return { title: t("title"), robots: { index: false } };
}

export default async function MyBookingsPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/account/bookings", locale });
    return null;
  }
  const role = query.role === "owner" ? "owner" : "renter";
  const page = Math.max(1, Number(query.page) || 1);
  const [t, result] = await Promise.all([getTranslations(), listBookings(role, page, PAGE_SIZE)]);
  const items = result?.items ?? [];
  const isOwner = user.roles.includes("owner");
  const pairs: Pair[] = role === "owner" ? [["role", "owner"]] : [];

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("myBookings.title")} />
      {(isOwner || role === "owner") && (
        <FilterPills
          label={t("myBookings.title")}
          pills={[
            {
              href: "/account/bookings",
              label: t("myBookings.asRenter"),
              current: role === "renter",
            },
            {
              href: "/account/bookings?role=owner",
              label: t("myBookings.asOwner"),
              current: role === "owner",
            },
          ]}
        />
      )}

      {items.length === 0 ? (
        <EmptyState
          icon="calendar"
          action={
            role === "renter" && (
              <Link href="/search" className={buttonClasses("primary")}>
                {t("myBookings.find")}
              </Link>
            )
          }
        >
          {role === "owner" ? t("myBookings.emptyOwner") : t("myBookings.empty")}
        </EmptyState>
      ) : (
        <ul className="grid gap-4 xl:grid-cols-2">
          {items.map((b) => (
            <li key={b.id}>
              <Link
                href={`/book/${b.id}`}
                className="flex h-full gap-4 rounded-[var(--radius-card)] bg-card p-4 transition-colors hover:bg-brand-50"
              >
                <ImageWithFallback
                  src={b.listing.cover_photo?.url_320}
                  alt={b.listing.cover_photo?.alt ?? b.listing.title}
                  fallbackLabel={t("common.imageUnavailable")}
                  className="size-24 shrink-0 rounded-2xl"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-semibold text-ink">{b.listing.title}</p>
                    <BookingStatusBadge status={b.status} />
                  </div>
                  <p className="flex items-center gap-1.5 text-sm text-muted">
                    <Icon name="calendar" className="size-4 shrink-0" />
                    <span className="truncate">
                      {formatPeriod(
                        b.period,
                        b.listing.booking_mode,
                        b.listing.base_price?.unit,
                        locale,
                      )}
                    </span>
                  </p>
                  <p className="mt-auto flex items-center justify-between gap-2 rounded-2xl bg-surface px-3 py-2 text-sm">
                    <span className="font-mono text-xs text-muted">{b.code}</span>
                    <Money amount={b.total_tzs} className="font-semibold text-ink" />
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {result && (
        <Pagination
          pairs={pairs}
          page={page}
          pageSize={PAGE_SIZE}
          total={result.total}
          path="/account/bookings"
        />
      )}
    </div>
  );
}
