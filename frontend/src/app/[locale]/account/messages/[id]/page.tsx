import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { ConversationThread } from "@/components/ConversationThread";
import { Link, redirect } from "@/i18n/navigation";
import { getCurrentUser } from "@/lib/api/server";
import { getThread } from "@/lib/api/social";

type Props = { params: Promise<{ locale: string; id: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "messages" });
  return { title: t("title"), robots: { index: false } };
}

export default async function ConversationPage({ params }: Props) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  const user = await getCurrentUser();
  if (!user) {
    redirect({ href: `/account/sign-in?returnTo=/account/messages/${id}`, locale });
    return null;
  }
  const thread = UUID.test(id) ? await getThread(id) : null;
  if (!thread) notFound();
  const { conversation: c, messages } = thread;
  const t = await getTranslations("messages");

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <nav className="text-sm">
        <Link href="/account/messages" className="text-brand-700 hover:underline">
          ← {t("title")}
        </Link>
      </nav>
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-ink">{c.counterpart.name}</h1>
        <p className="text-sm text-muted">
          {t(c.role === "owner" ? "yourListingLabel" : "aboutLabel")}{" "}
          <Link href={`/l/${c.listing.id}`} className="text-brand-700 hover:underline">
            {c.listing.title}
          </Link>
          {c.booking_id && (
            <>
              {" · "}
              <Link href={`/book/${c.booking_id}`} className="text-brand-700 hover:underline">
                {t("viewBooking")}
              </Link>
            </>
          )}
        </p>
      </header>
      <ConversationThread
        conversationId={c.id}
        initial={messages}
        revealed={c.booking_id != null}
      />
    </div>
  );
}
