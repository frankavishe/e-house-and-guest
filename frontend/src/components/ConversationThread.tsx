"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { Button } from "./ui/Button";

type Message = Schemas["MessageOut"];

const POLL_MS = 10_000;

function merge(current: Message[], incoming: Message[]): Message[] {
  const seen = new Set(current.map((m) => m.seq));
  return [...current, ...incoming.filter((m) => !seen.has(m.seq))].sort((a, b) => a.seq - b.seq);
}

/** A conversation's messages, polled every 10 s while open (FR-028), with a reply box.
 * Phone numbers are masked by the server until a booking is confirmed (R18). */
export function ConversationThread({
  conversationId,
  initial,
  revealed,
}: {
  conversationId: string;
  initial: Message[];
  revealed: boolean;
}) {
  const t = useTranslations("messages");
  const tErr = useTranslations("errors");
  const locale = useLocale() === "en" ? "en" : "sw";
  const [messages, setMessages] = useState(initial);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const lastSeq = messages.length ? messages[messages.length - 1].seq : 0;
  const path = { conversation_id: conversationId };

  const poll = useCallback(async () => {
    try {
      const { data } = await api.GET("/api/v1/conversations/{conversation_id}/messages", {
        params: { path: { conversation_id: conversationId }, query: { after: lastSeq } },
      });
      if (data?.items.length) setMessages((current) => merge(current, data.items));
    } catch {
      // offline: try again on the next tick
    }
  }, [conversationId, lastSeq]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") poll();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [poll]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = body.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST(
        "/api/v1/conversations/{conversation_id}/messages",
        { params: { path }, body: { body: text } },
      );
      if (data) {
        setMessages((current) => merge(current, [data]));
        setBody("");
      } else setError(apiError(err)?.message ?? tErr("generic"));
    } catch {
      setError(tErr("network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {!revealed && <p className="rounded-lg bg-canvas p-3 text-xs text-muted">{t("maskNote")}</p>}
      <ol className="flex flex-col gap-2" aria-live="polite">
        {messages.length === 0 && <li className="text-sm text-muted">{t("noMessages")}</li>}
        {messages.map((m) => (
          <li
            key={m.seq}
            className={`flex max-w-[85%] flex-col gap-0.5 rounded-2xl px-3 py-2 text-sm ${
              m.mine
                ? "self-end bg-brand-600 text-white"
                : "self-start border border-line bg-surface text-ink"
            }`}
          >
            <p className="whitespace-pre-line break-words">{m.body}</p>
            <p className={`text-[11px] ${m.mine ? "text-white/80" : "text-muted"}`}>
              {formatDateTime(m.created_at, locale)}
              {m.masked ? ` · ${t("masked")}` : ""}
              {m.mine && m.read_at ? ` · ${t("read")}` : ""}
            </p>
          </li>
        ))}
      </ol>
      <div ref={endRef} />
      <form onSubmit={send} className="flex flex-col gap-2">
        <label className="sr-only" htmlFor="reply">
          {t("reply")}
        </label>
        <textarea
          id="reply"
          rows={3}
          maxLength={2000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={t("placeholder")}
          className="rounded-lg border border-line bg-surface p-3 text-sm text-ink"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end">
          <Button type="submit" loading={busy} disabled={!body.trim()}>
            {t("send")}
          </Button>
        </div>
      </form>
    </div>
  );
}
