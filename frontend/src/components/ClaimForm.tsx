"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { uploadFile } from "@/lib/upload";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Kind = Schemas["ClaimIn"]["kind"];

const MAX_FILES = 10;
const ACCEPT = "image/jpeg,image/png,application/pdf";

/** Report a problem (FR-027): a damage claim on the deposit (owner) or a dispute (either
 * party), with optional photos or documents uploaded straight to storage. */
export function ClaimForm({
  bookingId,
  canClaimDamage,
}: {
  bookingId: string;
  canClaimDamage: boolean;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>(canClaimDamage ? "damage" : "dispute");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [keys, setKeys] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const path = { booking_id: bookingId };

  async function addFiles(files: FileList | null) {
    if (!files) return;
    setUploading(true);
    setError(null);
    try {
      const added: string[] = [];
      for (const file of Array.from(files).slice(0, MAX_FILES - keys.length)) {
        const key = await uploadFile(async () => {
          const { data } = await api.POST("/api/v1/bookings/{booking_id}/claims/evidence-upload", {
            params: { path },
            body: { content_type: file.type },
          });
          return data;
        }, file);
        if (!key) {
          setError(t("claim.uploadFailed"));
          break;
        }
        added.push(key);
      }
      setKeys((current) => [...current, ...added]);
    } catch {
      setError(t("errors.network"));
    } finally {
      setUploading(false);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/bookings/{booking_id}/claims", {
        params: { path },
        body: {
          kind,
          description: description.trim(),
          amount_claimed_tzs: amount ? Number(amount) : null,
          evidence_keys: keys,
        },
      });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else {
        setOpen(false);
        router.refresh();
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted">{t("claim.window")}</p>
        <div>
          <Button variant="secondary" onClick={() => setOpen(true)}>
            {t("claim.open")}
          </Button>
        </div>
      </div>
    );
  }

  const kinds: Kind[] = canClaimDamage ? ["damage", "dispute"] : ["dispute"];
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Select
        label={t("claim.kind")}
        options={kinds.map((k) => ({ value: k, label: t(`claim.kind_${k}`) }))}
        value={kind}
        onChange={(e) => setKind(e.target.value as Kind)}
      />
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("claim.description")}</span>
        <textarea
          rows={4}
          required
          maxLength={2000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="rounded-2xl border border-line bg-surface p-4 text-base text-ink focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100"
        />
      </label>
      {kind === "damage" && (
        <Input
          label={t("claim.amount")}
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      )}
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("claim.evidence")}</span>
        <input
          type="file"
          accept={ACCEPT}
          multiple
          disabled={uploading || keys.length >= MAX_FILES}
          onChange={(e) => addFiles(e.target.files)}
          className="text-sm text-ink"
        />
        <span className="text-sm text-muted">
          {uploading ? t("claim.uploading") : t("claim.files", { count: keys.length })}
        </span>
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={busy} disabled={uploading || !description.trim()}>
          {t("claim.submit")}
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>
          {t("common.back")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </form>
  );
}
