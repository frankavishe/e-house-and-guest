"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Link } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";

/** Report a listing or user to the admins (FR-030). */
export function ReportButton({
  targetKind,
  targetId,
  signedIn,
  returnTo,
}: {
  targetKind: "listing" | "user";
  targetId: string;
  signedIn: boolean;
  returnTo: string;
}) {
  const t = useTranslations("report");
  const tErr = useTranslations("errors");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = t(targetKind === "listing" ? "listing" : "user");

  if (!signedIn) {
    return (
      <Link
        href={`/account/sign-in?returnTo=${returnTo}`}
        className="text-sm text-muted underline hover:text-ink"
      >
        {label}
      </Link>
    );
  }
  if (done) return <p className="text-sm text-muted">{t("thanks")}</p>;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/reports", {
        body: { target_kind: targetKind, target_id: targetId, reason: reason.trim() },
      });
      if (err) setError(apiError(err)?.message ?? tErr("generic"));
      else setDone(true);
    } catch {
      setError(tErr("network"));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start text-sm text-muted underline hover:text-ink"
      >
        {label}
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("reason")}</span>
        <textarea
          rows={3}
          required
          maxLength={1000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="rounded-lg border border-line bg-surface p-3 text-sm text-ink"
        />
      </label>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" variant="danger" loading={busy} disabled={!reason.trim()}>
          {t("submit")}
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
