"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";

type Listing = Schemas["OwnerListingOut"];
type Unit = Schemas["PriceRow"]["unit"];
type Season = { unit: Unit; amount: string; start: string; end: string };

const amountOf = (v: string) => Math.round(Number(v.replace(/[^\d]/g, "")));

/** Prices per unit, seasonal prices, deposit and delivery. Price edits apply at once,
 * even on a live listing. */
export function PriceEditor({
  listing,
  onSaved,
}: {
  listing: Listing;
  onSaved: (listing: Listing) => void;
}) {
  const t = useTranslations();
  const units = listing.category.price_units as Unit[];
  const [base, setBase] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      units.map((u) => [
        u,
        String(listing.prices.find((p) => p.unit === u && !p.season_start)?.amount_tzs ?? ""),
      ]),
    ),
  );
  const [seasons, setSeasons] = useState<Season[]>(() =>
    listing.prices
      .filter((p) => p.season_start)
      .map((p) => ({
        unit: p.unit,
        amount: String(p.amount_tzs),
        start: p.season_start ?? "",
        end: p.season_end ?? "",
      })),
  );
  const [deposit, setDeposit] = useState(String(listing.deposit_tzs || ""));
  const [delivery, setDelivery] = useState(listing.delivery);
  const [deliveryFee, setDeliveryFee] = useState(String(listing.delivery_fee_tzs ?? ""));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const unitLabel = (u: string) => t(`units.${u}`);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const rows: Schemas["PriceRow"][] = [
        ...units.filter((u) => base[u]).map((u) => ({ unit: u, amount_tzs: amountOf(base[u]) })),
        ...seasons
          .filter((s) => s.amount && s.start && s.end)
          .map((s) => ({
            unit: s.unit,
            amount_tzs: amountOf(s.amount),
            season_start: s.start,
            season_end: s.end,
          })),
      ];
      const path = { listing_id: listing.id };
      const prices = await api.PUT("/api/v1/owner/listings/{listing_id}/prices", {
        params: { path },
        body: rows,
      });
      if (prices.error) {
        setError(apiError(prices.error)?.message ?? t("errors.generic"));
        return;
      }
      const { data, error: err } = await api.PATCH("/api/v1/owner/listings/{listing_id}", {
        params: { path },
        body: {
          deposit_tzs: deposit ? amountOf(deposit) : 0,
          delivery,
          delivery_fee_tzs: delivery === "none" || !deliveryFee ? null : amountOf(deliveryFee),
        },
      });
      if (data) onSaved(data);
      else setError(apiError(err)?.message ?? t("errors.generic"));
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const setSeason = (i: number, patch: Partial<Season>) =>
    setSeasons((list) => list.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      {units.map((u) => (
        <Input
          key={u}
          label={t("wizard.pricePer", { unit: unitLabel(u) })}
          hint={u === listing.category.default_unit ? t("wizard.basePriceHint") : undefined}
          required={u === listing.category.default_unit}
          inputMode="numeric"
          value={base[u] ?? ""}
          onChange={(e) => setBase((b) => ({ ...b, [u]: e.target.value }))}
        />
      ))}

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-medium text-ink">{t("wizard.seasons")}</legend>
        <p className="text-sm text-muted">{t("wizard.seasonsHint")}</p>
        {seasons.map((s, i) => (
          <div key={i} className="grid grid-cols-2 gap-2 rounded-2xl border border-line bg-surface p-3">
            {units.length > 1 && (
              <div className="col-span-2">
                <Select
                  label={t("wizard.unit")}
                  value={s.unit}
                  onChange={(e) => setSeason(i, { unit: e.target.value as Unit })}
                  options={units.map((u) => ({ value: u, label: unitLabel(u) }))}
                />
              </div>
            )}
            <Input label={t("wizard.seasonFrom")} type="date" value={s.start} onChange={(e) => setSeason(i, { start: e.target.value })} />
            <Input label={t("wizard.seasonTo")} type="date" min={s.start} value={s.end} onChange={(e) => setSeason(i, { end: e.target.value })} />
            <div className="col-span-2">
              <Input
                label={t("wizard.pricePer", { unit: unitLabel(s.unit) })}
                inputMode="numeric"
                value={s.amount}
                onChange={(e) => setSeason(i, { amount: e.target.value })}
              />
            </div>
            <Button
              variant="ghost"
              className="col-span-2 text-danger"
              onClick={() => setSeasons((list) => list.filter((_, j) => j !== i))}
            >
              {t("wizard.remove")}
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          onClick={() =>
            setSeasons((list) => [...list, { unit: units[0], amount: "", start: "", end: "" }])
          }
        >
          {t("wizard.addSeason")}
        </Button>
      </fieldset>

      <Input
        label={t("wizard.deposit")}
        hint={t("wizard.depositHint")}
        inputMode="numeric"
        value={deposit}
        onChange={(e) => setDeposit(e.target.value)}
      />
      <Select
        label={t("wizard.delivery")}
        value={delivery}
        onChange={(e) => setDelivery(e.target.value as Listing["delivery"])}
        options={(["none", "optional", "required"] as const).map((d) => ({
          value: d,
          label: t(`wizard.delivery_${d}`),
        }))}
      />
      {delivery !== "none" && (
        <Input
          label={t("wizard.deliveryFee")}
          hint={t("wizard.deliveryFeeHint")}
          inputMode="numeric"
          value={deliveryFee}
          onChange={(e) => setDeliveryFee(e.target.value)}
        />
      )}

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" full loading={busy}>
        {t("wizard.saveContinue")}
      </Button>
    </form>
  );
}
