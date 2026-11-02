"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";

/** Account deletion (FR-033): a collapsed danger zone with an explicit confirmation. */
export function DeleteAccount() {
  const t = useTranslations("account.delete");
  const tr = useTranslations();
  const router = useRouter();
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const { response, error: err } = await api.DELETE("/api/v1/me");
      if (response.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      setError(apiError(err)?.message ?? tr("errors.generic"));
    } catch {
      setError(tr("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-[var(--radius-card)] bg-card p-4">
      <summary className="cursor-pointer text-sm font-medium text-danger">{t("title")}</summary>
      <div className="mt-3 flex flex-col gap-3 text-sm text-ink">
        <p>{t("explain")}</p>
        <p className="text-muted">{t("kept")}</p>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="size-5 accent-danger"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          {t("confirm")}
        </label>
        {error && (
          <p role="alert" className="text-danger">
            {error}
          </p>
        )}
        <Button variant="danger" disabled={!confirmed} loading={busy} onClick={remove}>
          {t("button")}
        </Button>
      </div>
    </details>
  );
}
