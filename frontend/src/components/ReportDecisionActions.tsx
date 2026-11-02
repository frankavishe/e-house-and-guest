"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Handle an abuse report: dismiss it, or action it (closing every open report on the same
 * target), optionally suspending the reported listing or user. */
export function ReportDecisionActions({ id, canSuspend }: { id: string; canSuspend: boolean }) {
  const t = useTranslations();
  const router = useRouter();
  const [note, setNote] = useState("");
  const [suspend, setSuspend] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"actioned" | "dismissed" | null>(null);

  async function decide(decision: "actioned" | "dismissed") {
    setBusy(decision);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/admin/reports-abuse/{report_id}/action", {
        params: { path: { report_id: id } },
        body: {
          decision,
          suspend_target: decision === "actioned" && suspend,
          note: note.trim() || null,
        },
      });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <Input
        label={t("adminReports.note")}
        hint={suspend ? t("adminReports.noteHint") : undefined}
        maxLength={500}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {canSuspend && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={suspend} onChange={(e) => setSuspend(e.target.checked)} />
          {t("adminReports.suspendTarget")}
        </label>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={suspend ? "danger" : "primary"}
          loading={busy === "actioned"}
          disabled={busy !== null}
          onClick={() => decide("actioned")}
        >
          {t("adminReports.action")}
        </Button>
        <Button
          variant="secondary"
          loading={busy === "dismissed"}
          disabled={busy !== null}
          onClick={() => decide("dismissed")}
        >
          {t("adminReports.dismiss")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
