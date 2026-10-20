import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { BookingStatusBadge } from "@/components/BookingStatusBadge";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { Money } from "@/components/Money";
import { Pagination } from "@/components/Pagination";
import { buttonClasses } from "@/components/ui/Button";
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

  const tab = (value: "renter" | "owner", label: string) => (
    <Link
      href={value === "owner" ? "/account/bookings?role=owner" : "/account/bookings"}
      aria-current={role === value ? "page" : undefined}
      className={`rounded-full px-3 py-1.5 text-sm font-medium ${
        role === value ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <h1 className="text-xl font-bold text-ink">{t("myBookings.title")}</h1>
      {(isOwner || role === "owner") && (
        <nav className="flex gap-2">
          {tab("renter", t("myBookings.asRenter"))}
          {tab("owner", t("myBookings.asOwner"))}
        </nav>
      )}

      {items.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-line p-4">
          <p className="text-muted">
            {role === "owner" ? t("myBookings.emptyOwner") : t("myBookings.empty")}
          </p>
          {role === "renter" && (
            <Link href="/search" className={buttonClasses("primary")}>
              {t("myBookings.find")}
            </Link>
          )}
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((b) => (
            <li key={b.id}>
              <Link
                href={`/book/${b.id}`}
                className="flex gap-3 rounded-xl border border-line bg-surface p-3 hover:border-brand-600"
              >
                <ImageWithFallback
                  src={b.listing.cover_photo?.url_320}
                  alt={b.listing.cover_photo?.alt ?? b.listing.title}
                  fallbackLabel={t("common.imageUnavailable")}
                  className="size-20 shrink-0 rounded-lg"
                />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-medium text-ink">{b.listing.title}</p>
                    <BookingStatusBadge status={b.status} />
                  </div>
                  <p className="text-sm text-muted">
                    {formatPeriod(
                      b.period,
                      b.listing.booking_mode,
                      b.listing.base_price?.unit,
                      locale,
                    )}
                  </p>
                  <p className="flex justify-between text-sm">
                    <span className="text-muted">{b.code}</span>
                    <Money amount={b.total_tzs} className="font-medium text-ink" />
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
