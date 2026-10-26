"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { uploadFile } from "@/lib/upload";
import { Badge } from "./ui/Badge";
import { Button, buttonClasses } from "./ui/Button";
import { Input } from "./ui/Input";

type Profile = Schemas["OwnerProfileOut"];
type Kind = Profile["kind"];

const STATUS_TONE = {
  draft: "neutral",
  pending: "warning",
  verified: "brand",
  rejected: "danger",
} as const;

/** Become an owner: identity details, documents, submit for verification, status. */
export function OwnerOnboarding({ profile }: { profile: Profile | null }) {
  const t = useTranslations();
  const router = useRouter();
  const [kind, setKind] = useState<Kind>(profile?.kind ?? "individual");
  const [form, setForm] = useState({
    display_name: profile?.display_name ?? "",
    nida_number: "",
    business_name: profile?.business_name ?? "",
    brela_reg_no: profile?.brela_reg_no ?? "",
    tin: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const editable = !profile || profile.verification_status === "draft" || profile.verification_status === "rejected";

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value })),
  });

  async function run(action: () => Promise<{ error?: unknown } | void>) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      if (result && result.error) {
        setError(apiError(result.error)?.message ?? t("errors.generic"));
        return;
      }
      router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const blankToUndefined = (v: string) => v.trim() || undefined;

  function save(e: FormEvent) {
    e.preventDefault();
    return run(async () => {
      if (!profile) {
        return api.POST("/api/v1/owner-profile", {
          body: {
            kind,
            display_name: form.display_name,
            nida_number: kind === "individual" ? blankToUndefined(form.nida_number) : undefined,
            business_name: kind === "business" ? blankToUndefined(form.business_name) : undefined,
            brela_reg_no: kind === "business" ? blankToUndefined(form.brela_reg_no) : undefined,
            tin: kind === "business" ? blankToUndefined(form.tin) : undefined,
          },
        });
      }
      return api.PATCH("/api/v1/owner-profile", {
        body: {
          display_name: blankToUndefined(form.display_name),
          nida_number: blankToUndefined(form.nida_number),
          business_name: blankToUndefined(form.business_name),
          brela_reg_no: blankToUndefined(form.brela_reg_no),
          tin: blankToUndefined(form.tin),
        },
      });
    });
  }

  const submit = () => run(() => api.POST("/api/v1/owner-profile/submit"));

  const addDocument = (file: File) =>
    run(async () => {
      if (!profile) return;
      const key = await uploadFile(async () => {
        const { data } = await api.POST("/api/v1/owner-profile/documents", {
          body: { content_type: file.type },
        });
        return data;
      }, file);
      if (!key) {
        setError(t("owner.uploadFailed"));
        return;
      }
      return api.PATCH("/api/v1/owner-profile", {
        body: { documents: [...profile.documents, key] },
      });
    });

  return (
    <div className="flex flex-col gap-5">
      {profile && (
        <section className="flex flex-col gap-2 rounded-3xl bg-card p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-ink">{profile.display_name}</h2>
            <Badge tone={STATUS_TONE[profile.verification_status]}>
              {t(`owner.status.${profile.verification_status}`)}
            </Badge>
          </div>
          <p className="text-sm text-muted">{t(`owner.statusHint.${profile.verification_status}`)}</p>
          {profile.verification_status === "rejected" && profile.rejection_reason && (
            <p role="alert" className="text-sm text-danger">
              {t("owner.rejectedBecause", { reason: profile.rejection_reason })}
            </p>
          )}
          {(profile.verification_status === "verified" || profile.verification_status === "pending") && (
            <Link href="/owner/listings" className={buttonClasses("primary")}>
              {t("owner.goToListings")}
            </Link>
          )}
        </section>
      )}

      {editable && (
        <form onSubmit={save} className="flex flex-col gap-3">
          {!profile && (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium text-ink">{t("owner.kind")}</legend>
              <div className="grid grid-cols-2 gap-2">
                {(["individual", "business"] as const).map((k) => (
                  <label
                    key={k}
                    className={`flex h-12 cursor-pointer items-center gap-2 rounded-2xl border px-3 text-sm ${
                      kind === k ? "border-brand-600 bg-brand-50 font-medium" : "border-line"
                    }`}
                  >
                    <input
                      type="radio"
                      name="kind"
                      checked={kind === k}
                      onChange={() => setKind(k)}
                      className="accent-brand-600"
                    />
                    {t(`owner.kind_${k}`)}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <Input label={t("owner.displayName")} hint={t("owner.displayNameHint")} required maxLength={200} {...field("display_name")} />
          {kind === "individual" ? (
            <Input
              label={t("owner.nida")}
              hint={profile?.nida_number_masked ? t("owner.onFile", { masked: profile.nida_number_masked }) : t("owner.nidaHint")}
              required={!profile}
              inputMode="numeric"
              maxLength={40}
              {...field("nida_number")}
            />
          ) : (
            <>
              <Input label={t("owner.businessName")} required={!profile} maxLength={200} {...field("business_name")} />
              <Input label={t("owner.brela")} required={!profile} maxLength={40} {...field("brela_reg_no")} />
              <Input
                label={t("owner.tin")}
                hint={profile?.tin_masked ? t("owner.onFile", { masked: profile.tin_masked }) : undefined}
                required={!profile}
                inputMode="numeric"
                maxLength={40}
                {...field("tin")}
              />
            </>
          )}
          <Button type="submit" variant={profile ? "secondary" : "primary"} size="lg" full loading={busy}>
            {profile ? t("owner.save") : t("owner.create")}
          </Button>
        </form>
      )}

      {profile && editable && (
        <section className="flex flex-col gap-3 border-t border-line pt-4">
          <h2 className="text-base font-semibold text-ink">{t("owner.documents")}</h2>
          <p className="text-sm text-muted">{t("owner.documentsHint")}</p>
          {profile.documents.length > 0 && (
            <p className="text-sm text-ink">{t("owner.documentCount", { count: profile.documents.length })}</p>
          )}
          <label className={`${buttonClasses("secondary")} cursor-pointer`}>
            {t("owner.addDocument")}
            <input
              type="file"
              accept="image/jpeg,image/png,application/pdf"
              className="sr-only"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) addDocument(file);
                e.target.value = "";
              }}
            />
          </label>
          <Button size="lg" full loading={busy} onClick={submit}>
            {t("owner.submit")}
          </Button>
        </section>
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
