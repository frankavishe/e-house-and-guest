"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Resolution = Schemas["ResolveClaimIn"]["resolution"];
const RESOLUTIONS: Resolution[] = ["owner_awarded", "split", "renter_refunded"];

/** Decide a claim: how much of the held deposit the owner gets; the rest is refunded. */
export function ClaimResolveActions({ id, deposit }: { id: string; deposit: number }) {
  const t = useTranslations();
  const router = useRouter();
  const [resolution, setResolution] = useState<Resolution>(
    deposit > 0 ? "owner_awarded" : "renter_refunded",
  );
  const [award, setAward] = useState(String(deposit));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const withAward = resolution !== "renter_refunded";

  async function resolve() {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/admin/claims/{claim_id}/resolve", {
        params: { path: { claim_id: id } },
        body: {
          resolution,
          amount_awarded_tzs: withAward ? Number(award) : null,
          note: note.trim() || null,
        },
      });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <Select
        label={t("adminClaims.resolution")}
        options={RESOLUTIONS.filter((r) => deposit > 0 || r === "renter_refunded").map((r) => ({
          value: r,
          label: t(`claim.resolution_${r}`),
        }))}
        value={resolution}
        onChange={(e) => setResolution(e.target.value as Resolution)}
      />
      {withAward && (
        <Input
          label={t("adminClaims.award")}
          hint={t("adminClaims.awardHint")}
          type="number"
          inputMode="numeric"
          min={0}
          max={deposit}
          step={1}
          value={award}
          onChange={(e) => setAward(e.target.value)}
        />
      )}
      <Input
        label={t("adminClaims.note")}
        maxLength={1000}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div>
        <Button loading={busy} onClick={resolve}>
          {t("adminClaims.resolve")}
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
