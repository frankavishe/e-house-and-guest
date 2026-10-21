"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import type { PayoutStatus } from "@/lib/api/owner";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Admin payout buttons (R7): mark paid with the transfer reference, or retry a failure. */
export function PayoutActions({ id, status }: { id: string; status: PayoutStatus }) {
  const t = useTranslations();
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [ref, setRef] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: "mark-paid" | "retry") {
    setBusy(true);
    setError(null);
    const path = { params: { path: { payout_id: id } } };
    try {
      const { error: err } =
        action === "retry"
          ? await api.POST("/api/v1/admin/payouts/{payout_id}/retry", path)
          : await api.POST("/api/v1/admin/payouts/{payout_id}/mark-paid", {
              ...path,
              body: { provider_ref: ref.trim() },
            });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        setAsking(false);
        setRef("");
        router.refresh();
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  if (status === "paid") return null;
  return (
    <div className="flex flex-col gap-2">
      {asking ? (
        <>
          <Input
            label={t("adminPayouts.reference")}
            hint={t("adminPayouts.referenceHint")}
            required
            maxLength={100}
            value={ref}
            onChange={(e) => setRef(e.target.value)}
          />
          <div className="flex gap-2">
            <Button loading={busy} disabled={!ref.trim()} onClick={() => run("mark-paid")}>
              {t("adminPayouts.confirmPaid")}
            </Button>
            <Button variant="secondary" onClick={() => setAsking(false)}>
              {t("common.back")}
            </Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setAsking(true)}>{t("adminPayouts.markPaid")}</Button>
          {status === "failed" && (
            <Button variant="secondary" loading={busy} onClick={() => run("retry")}>
              {t("adminPayouts.retry")}
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
