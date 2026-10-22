import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { Pagination } from "@/components/Pagination";
import { Link, redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { getInbox } from "@/lib/api/social";
import { formatDateTime } from "@/lib/format";

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ page?: string }>;
};

const PAGE_SIZE = 20;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "messages" });
  return { title: t("title"), robots: { index: false } };
}

/** The inbox: conversations as renter and as owner, with unread counts (FR-028). */
export default async function InboxPage({ params, searchParams }: Props) {
  const [{ locale: raw }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(raw);
  const locale = raw === "en" ? "en" : "sw";
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: "/account/sign-in?returnTo=/account/messages", locale });
    return null;
  }
  const page = Math.max(1, Number(query.page) || 1);
  const [t, inbox] = await Promise.all([getTranslations(), getInbox(page, PAGE_SIZE)]);
  const items = inbox?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <h1 className="text-xl font-bold text-ink">{t("messages.title")}</h1>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("messages.empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((c) => (
            <li key={c.id}>
              <Link
                href={`/account/messages/${c.id}`}
                className="flex items-center gap-3 p-3 hover:bg-canvas"
              >
                <ImageWithFallback
                  src={c.listing.photo_url}
                  alt={c.listing.title}
                  fallbackLabel={t("common.imageUnavailable")}
                  sizes="56px"
                  className="size-14 shrink-0 rounded-lg"
                />
                <div className="min-w-0 flex-1">
                  <p className="flex items-baseline justify-between gap-2">
                    <span
                      className={`truncate text-sm ${c.unread_count ? "font-bold" : "font-medium"} text-ink`}
                    >
                      {c.counterpart.name}
                    </span>
                    {c.last_message_at && (
                      <span className="shrink-0 text-xs text-muted">
                        {formatDateTime(c.last_message_at, locale)}
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {t(c.role === "owner" ? "messages.yourListing" : "messages.aboutListing", {
                      title: c.listing.title,
                    })}
                  </p>
                  <p className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-muted">{c.last_message}</span>
                    {c.unread_count > 0 && (
                      <span className="shrink-0 rounded-full bg-brand-600 px-2 text-xs font-bold leading-5 text-white">
                        {c.unread_count}
                      </span>
                    )}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {inbox && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={inbox.total}
          path="/account/messages"
          pairs={[]}
        />
      )}
    </div>
  );
}
