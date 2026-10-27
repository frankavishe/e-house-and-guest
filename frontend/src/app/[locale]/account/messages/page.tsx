import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ImageWithFallback } from "@/components/ImageWithFallback";
import { Pagination } from "@/components/Pagination";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
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
    <div className="flex w-full flex-col gap-5">
      <PageHeader title={t("messages.title")} />
      {items.length === 0 ? (
        <EmptyState icon="message">{t("messages.empty")}</EmptyState>
      ) : (
        <ul className="flex flex-col gap-1 rounded-[var(--radius-card)] bg-card p-2">
          {items.map((c) => (
            <li key={c.id}>
              <Link
                href={`/account/messages/${c.id}`}
                className="flex items-center gap-3 rounded-2xl p-3 transition-colors hover:bg-surface"
              >
                <ImageWithFallback
                  src={c.listing.photo_url}
                  alt={c.listing.title}
                  fallbackLabel={t("common.imageUnavailable")}
                  sizes="56px"
                  className="size-14 shrink-0 rounded-2xl"
                />
                <div className="min-w-0 flex-1">
                  <p className="flex items-baseline justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-2">
                      {c.unread_count > 0 && (
                        <span aria-hidden className="size-2 shrink-0 rounded-full bg-brand-600" />
                      )}
                      <span
                        className={`truncate text-sm ${c.unread_count ? "font-semibold" : "font-medium"} text-ink`}
                      >
                        {c.counterpart.name}
                      </span>
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
                    <span
                      className={`truncate text-sm ${c.unread_count ? "text-ink" : "text-muted"}`}
                    >
                      {c.last_message}
                    </span>
                    {c.unread_count > 0 && (
                      <span className="shrink-0 rounded-full bg-brand-600 px-2 text-xs font-semibold leading-5 text-white">
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
