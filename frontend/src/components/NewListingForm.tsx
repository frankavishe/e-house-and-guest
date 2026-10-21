"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Select, type Option } from "./ui/Select";

/** Pick a leaf category; creates the draft and opens the wizard. */
export function NewListingForm({ categories }: { categories: Option[] }) {
  const t = useTranslations();
  const router = useRouter();
  const [categoryId, setCategoryId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { data, error: err } = await api.POST("/api/v1/owner/listings", {
        body: { category_id: categoryId },
      });
      if (data) {
        router.push(`/owner/listings/${data.id}/edit`);
        return;
      }
      setError(apiError(err)?.message ?? t("errors.generic"));
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={create} className="flex flex-col gap-3">
      <Select
        label={t("ownerListings.category")}
        placeholder=""
        required
        value={categoryId}
        onChange={(e) => setCategoryId(e.target.value)}
        options={categories}
        error={error}
      />
      <Button type="submit" size="lg" full loading={busy} disabled={!categoryId}>
        {t("ownerListings.start")}
      </Button>
    </form>
  );
}
