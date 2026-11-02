"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api/client";
import { Button } from "./ui/Button";

/** Ends the session: revokes the refresh token and clears the auth cookies. */
export function SignOut() {
  const t = useTranslations();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    setBusy(true);
    setError(null);
    try {
      await api.POST("/api/v1/auth/logout");
      router.replace("/");
      router.refresh();
    } catch {
      setError(t("errors.network"));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button variant="secondary" loading={busy} onClick={signOut}>
        {t("account.signOut")}
      </Button>
    </div>
  );
}
