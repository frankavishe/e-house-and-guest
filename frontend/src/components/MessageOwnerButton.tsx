"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button, buttonClasses } from "./ui/Button";

/** Ask the owner a question before booking (FR-028); opens the conversation once sent. */
export function MessageOwnerButton({
  listingId,
  signedIn,
}: {
  listingId: string;
  signedIn: boolean;
}) {
  const t = useTranslations("messages");
  const tErr = useTranslations("errors");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!signedIn) {
    return (
      <Link
        href={`/account/sign-in?returnTo=/l/${listingId}`}
        className={buttonClasses("secondary")}
      >
        {t("messageOwner")}
      </Link>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST("/api/v1/conversations", {
        body: { listing_id: listingId, body: body.trim() },
      });
      if (data) router.push(`/account/messages/${data.id}`);
      else setError(apiError(err)?.message ?? tErr("generic"));
    } catch {
      setError(tErr("network"));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div>
        <Button variant="secondary" onClick={() => setOpen(true)}>
          {t("messageOwner")}
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("askOwner")}</span>
        <textarea
          rows={3}
          required
          maxLength={2000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={t("askPlaceholder")}
          className="rounded-lg border border-line bg-surface p-3 text-sm text-ink"
        />
      </label>
      <p className="text-xs text-muted">{t("maskNote")}</p>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" loading={busy} disabled={!body.trim()}>
          {t("send")}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
