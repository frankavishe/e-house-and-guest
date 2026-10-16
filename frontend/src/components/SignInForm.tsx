"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, apiError } from "@/lib/api/client";
import { safeReturnTo, withLocale } from "@/lib/returnTo";

type Step = "phone" | "code" | "name";

export function SignInForm({ returnTo }: { returnTo: string }) {
  const t = useTranslations();
  const locale = useLocale();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function finish() {
    // Full navigation so server components re-render with the new session cookies.
    window.location.assign(withLocale(safeReturnTo(returnTo), locale));
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const requestCode = (e?: FormEvent) => {
    e?.preventDefault();
    return run(async () => {
      const { error: err } = await api.POST("/api/v1/auth/otp/request", { body: { phone } });
      if (err) {
        setError(apiError(err)?.message ?? t("errors.generic"));
        return;
      }
      setCode("");
      setStep("code");
    });
  };

  const verify = (e: FormEvent) => {
    e.preventDefault();
    return run(async () => {
      const { data, error: err } = await api.POST("/api/v1/auth/otp/verify", {
        body: { phone, code },
      });
      if (err || !data) {
        setError(apiError(err)?.message ?? t("errors.generic"));
        return;
      }
      if (data.is_new || !data.user.name) setStep("name");
      else finish();
    });
  };

  const saveName = (e: FormEvent) => {
    e.preventDefault();
    return run(async () => {
      const { error: err } = await api.PATCH("/api/v1/me", { body: { name, language: locale as "sw" | "en" } });
      if (err) {
        setError(apiError(err)?.message ?? t("errors.generic"));
        return;
      }
      finish();
    });
  };

  return (
    <div className="mx-auto flex w-full max-w-sm flex-col gap-5 py-4">
      <h1 className="text-2xl font-bold">{step === "name" ? t("signIn.nameTitle") : t("signIn.title")}</h1>

      {step === "phone" && (
        <form onSubmit={requestCode} className="flex flex-col gap-4" noValidate>
          <Input
            label={t("signIn.phoneLabel")}
            hint={t("signIn.phoneHint")}
            error={error}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="0712 345 678"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
          />
          <Button type="submit" size="lg" full loading={busy} disabled={!phone.trim()}>
            {t("signIn.sendCode")}
          </Button>
        </form>
      )}

      {step === "code" && (
        <form onSubmit={verify} className="flex flex-col gap-4" noValidate>
          <Input
            label={t("signIn.codeLabel")}
            hint={t("signIn.codeHint", { phone })}
            error={error}
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            autoFocus
            required
          />
          <Button type="submit" size="lg" full loading={busy} disabled={code.length !== 6}>
            {t("signIn.verify")}
          </Button>
          <div className="flex justify-between">
            <Button variant="ghost" onClick={() => { setStep("phone"); setError(null); }}>
              {t("signIn.changePhone")}
            </Button>
            <Button variant="ghost" onClick={() => requestCode()} disabled={busy}>
              {t("signIn.resend")}
            </Button>
          </div>
        </form>
      )}

      {step === "name" && (
        <form onSubmit={saveName} className="flex flex-col gap-4" noValidate>
          <Input
            label={t("signIn.nameLabel")}
            error={error}
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            autoFocus
            required
          />
          <Button type="submit" size="lg" full loading={busy} disabled={!name.trim()}>
            {t("signIn.save")}
          </Button>
        </form>
      )}
    </div>
  );
}
