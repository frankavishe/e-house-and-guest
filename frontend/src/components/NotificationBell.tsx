"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { Link } from "@/i18n/navigation";
import { api, type Schemas } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
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
        className="relative rounded-md p-2 text-ink hover:bg-canvas"
      >
        <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor">
          <path
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"
          />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold leading-4 text-white">
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
                className="self-end text-sm text-brand-700 hover:underline"
              >
                {t("notifications.markAllRead")}
              </button>
            )}
            <ul className="flex flex-col divide-y divide-line">
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
                  <li key={n.id} className="py-2">
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
