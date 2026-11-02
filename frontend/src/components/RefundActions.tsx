"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Admin buttons for a failed refund: send it again, or record a refund made by hand. */
export function RefundActions({ id }: { id: string }) {
  const t = useTranslations();
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [ref, setRef] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: "mark-sent" | "retry") {
    setBusy(true);
    setError(null);
    const path = { params: { path: { refund_id: id } } };
    try {
      const { error: err } =
        action === "retry"
          ? await api.POST("/api/v1/admin/refunds/{refund_id}/retry", path)
          : await api.POST("/api/v1/admin/refunds/{refund_id}/mark-sent", {
              ...path,
              body: { provider_ref: ref.trim() },
            });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        setAsking(false);
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
      {asking ? (
        <>
          <Input
            label={t("refunds.reference")}
            required
            maxLength={100}
            value={ref}
            onChange={(e) => setRef(e.target.value)}
          />
          <div className="flex gap-2">
            <Button loading={busy} disabled={!ref.trim()} onClick={() => run("mark-sent")}>
              {t("refunds.confirmSent")}
            </Button>
            <Button variant="secondary" onClick={() => setAsking(false)}>
              {t("common.back")}
            </Button>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" loading={busy} onClick={() => run("retry")}>
            {t("refunds.retry")}
          </Button>
          <Button variant="secondary" onClick={() => setAsking(true)}>
            {t("refunds.markSent")}
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
