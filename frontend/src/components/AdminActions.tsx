"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

type Target = { kind: "owner"; id: string } | { kind: "listing"; id: string; status: string };
type Action = "approve" | "reject" | "suspend" | "unsuspend";

/** Moderation buttons; reject and suspend ask for a reason the owner will see. */
export function AdminActions({ target }: { target: Target }) {
  const t = useTranslations();
  const router = useRouter();
  const [asking, setAsking] = useState<"reject" | "suspend" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(action: Action) {
    const body = { reason: reason.trim() };
    if (target.kind === "owner") {
      const path = { params: { path: { profile_id: target.id } } };
      return action === "approve"
        ? api.POST("/api/v1/admin/owner-verifications/{profile_id}/approve", path)
        : api.POST("/api/v1/admin/owner-verifications/{profile_id}/reject", { ...path, body });
    }
    const path = { params: { path: { listing_id: target.id } } };
    switch (action) {
      case "approve":
        return api.POST("/api/v1/admin/listings/{listing_id}/approve", path);
      case "reject":
        return api.POST("/api/v1/admin/listings/{listing_id}/reject", { ...path, body });
      case "suspend":
        return api.POST("/api/v1/admin/listings/{listing_id}/suspend", { ...path, body });
      default:
        return api.POST("/api/v1/admin/listings/{listing_id}/unsuspend", path);
    }
  }

  async function run(action: Action) {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await call(action);
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        setAsking(null);
        setReason("");
        router.refresh();
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const live = target.kind === "listing" && (target.status === "active" || target.status === "paused");
  const suspended = target.kind === "listing" && target.status === "suspended";

  return (
    <div className="flex flex-col gap-2">
      {asking ? (
        <>
          <Input
            label={t("admin.reason")}
            hint={t("admin.reasonHint")}
            required
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="flex gap-2">
            <Button variant="danger" loading={busy} disabled={!reason.trim()} onClick={() => run(asking)}>
              {t(`admin.${asking}`)}
            </Button>
            <Button variant="secondary" onClick={() => setAsking(null)}>
              {t("common.back")}
            </Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap gap-2">
          {!suspended && (
            <>
              <Button loading={busy} onClick={() => run("approve")}>
                {t("admin.approve")}
              </Button>
              <Button variant="secondary" onClick={() => setAsking("reject")}>
                {t("admin.reject")}
              </Button>
            </>
          )}
          {live && (
            <Button variant="ghost" className="text-danger" onClick={() => setAsking("suspend")}>
              {t("admin.suspend")}
            </Button>
          )}
          {suspended && (
            <Button loading={busy} onClick={() => run("unsuspend")}>
              {t("admin.unsuspend")}
            </Button>
          )}
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
