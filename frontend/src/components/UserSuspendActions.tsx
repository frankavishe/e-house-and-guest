"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Suspend a user (with a reason they receive by SMS) or lift the suspension (FR-030). */
export function UserSuspendActions({ id, suspended }: { id: string; suspended: boolean }) {
  const t = useTranslations();
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    const path = { params: { path: { user_id: id } } };
    try {
      const { error: err } = suspended
        ? await api.POST("/api/v1/admin/users/{user_id}/unsuspend", path)
        : await api.POST("/api/v1/admin/users/{user_id}/suspend", {
            ...path,
            body: { reason: reason.trim() },
          });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        setAsking(false);
        setReason("");
        router.refresh();
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {suspended ? (
        <div>
          <Button variant="secondary" loading={busy} onClick={run}>
            {t("admin.unsuspend")}
          </Button>
        </div>
      ) : asking ? (
        <>
          <Input
            label={t("admin.reason")}
            hint={t("adminUsers.reasonHint")}
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="flex gap-2">
            <Button variant="danger" loading={busy} disabled={!reason.trim()} onClick={run}>
              {t("adminUsers.confirmSuspend")}
            </Button>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              {t("report.cancel")}
            </Button>
          </div>
        </>
      ) : (
        <div>
          <Button variant="secondary" onClick={() => setAsking(true)}>
            {t("admin.suspend")}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
