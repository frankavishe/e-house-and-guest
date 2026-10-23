"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { api, apiError } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";

/** Block days on one listing's calendar (US3-AS3); quantity for stock items. */
export function BlockForm({
  listingId,
  stock,
  minDate,
}: {
  listingId: string;
  stock: number | null;
  minDate: string;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.POST("/api/v1/owner/listings/{listing_id}/blocks", {
        params: { path: { listing_id: listingId } },
        body: {
          start_date: start,
          end_date: end || start,
          quantity: stock ? Number(quantity) || 1 : 1,
          note: note.trim() || null,
        },
      });
      if (err) {
        setError(apiError(err)?.message ?? t("errors.generic"));
        return;
      }
      setStart("");
      setEnd("");
      setNote("");
      // Show the month the block starts in, so the struck-through days are visible.
      router.replace(`/owner/calendar?listing=${listingId}&month=${start.slice(0, 7)}`);
      router.refresh();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={add} className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-4">
      <h2 className="text-base font-semibold text-ink">{t("calendar.blockTitle")}</h2>
      <div className="grid grid-cols-2 gap-2">
        <Input label={t("calendar.from")} type="date" min={minDate} required value={start} onChange={(e) => setStart(e.target.value)} />
        <Input label={t("calendar.to")} type="date" min={start || minDate} value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      {stock != null && (
        <Input
          label={t("calendar.quantity", { stock })}
          type="number"
          inputMode="numeric"
          min={1}
          max={stock}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        />
      )}
      <Input label={t("calendar.note")} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" loading={busy}>
        {t("calendar.block")}
      </Button>
    </form>
  );
}

export function RemoveBlockButton({ listingId, blockId }: { listingId: string; blockId: string }) {
  const t = useTranslations("calendar");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="ghost"
      className="h-8 px-2 text-danger"
      loading={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await api.DELETE("/api/v1/owner/listings/{listing_id}/blocks/{block_id}", {
            params: { path: { listing_id: listingId, block_id: blockId } },
          });
          router.refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      {t("unblock")}
    </Button>
  );
}
