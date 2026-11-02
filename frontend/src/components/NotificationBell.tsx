"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { Link } from "@/i18n/navigation";
import { api, type Schemas } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { Icon } from "./icons";
import { Sheet } from "./ui/Sheet";

type Item = Schemas["NotificationOut"];

const COUNT_POLL_MS = 60_000;
const FEED_SIZE = 20;

/** Bell with the unread count; opens the in-app feed (FR-019). */
export function NotificationBell() {
  const t = useTranslations();
  const locale = useLocale() === "en" ? "en" : "sw";
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Item[] | null>(null);

  const load = useCallback(async (size: number) => {
    try {
      const { data } = await api.GET("/api/v1/notifications", {
        params: { query: { page: 1, page_size: size } },
      });
      if (!data) return;
      setUnread(data.unread_count);
      if (size > 1) setItems(data.items);
    } catch {
      // offline: keep the last count
    }
  }, []);

  useEffect(() => {
    load(1);
    const timer = setInterval(() => load(1), COUNT_POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (open) load(FEED_SIZE);
  }, [open, load]);

  async function markAllRead() {
    const { data } = await api.POST("/api/v1/notifications/read", { body: { ids: null } });
    if (data) setUnread(data.unread_count);
    const now = new Date().toISOString();
    setItems((prev) => prev?.map((n) => ({ ...n, read_at: n.read_at ?? now })) ?? null);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("notifications.open", { count: unread })}
        className="relative flex size-10 items-center justify-center rounded-full bg-card text-ink hover:bg-brand-50"
      >
        <Icon name="bell" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-[18px] items-center justify-center rounded-full bg-brand-600 px-1 text-[10px] font-bold leading-[18px] text-white ring-2 ring-surface">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title={t("notifications.title")}
        closeLabel={t("common.close")}
      >
        {items === null ? (
          <p className="text-sm text-muted">{t("common.loading")}</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted">{t("notifications.empty")}</p>
        ) : (
          <div className="flex flex-col gap-3">
            {unread > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="self-end rounded-full px-3 py-1 text-sm font-medium text-brand-700 hover:bg-brand-50"
              >
                {t("notifications.markAllRead")}
              </button>
            )}
            <ul className="flex flex-col gap-1">
              {items.map((n) => {
                const body = (
                  <>
                    <p className={`text-sm ${n.read_at ? "text-muted" : "font-medium text-ink"}`}>
                      {n.text}
                    </p>
                    <p className="text-xs text-muted">{formatDateTime(n.created_at, locale)}</p>
                  </>
                );
                const href =
                  n.event === "message.received"
                    ? "/account/messages"
                    : n.booking_id
                      ? `/book/${n.booking_id}`
                      : null;
                return (
                  <li key={n.id} className={`rounded-2xl px-3 py-2.5 ${n.read_at ? "" : "bg-brand-50"}`}>
                    {href ? (
                      <Link
                        href={href}
                        onClick={() => setOpen(false)}
                        className="block hover:underline"
                      >
                        {body}
                      </Link>
                    ) : (
                      body
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Sheet>
    </>
  );
}
