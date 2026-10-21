"use client";

import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { STEPS, type Step } from "@/lib/wizard";
import { AttributeForm, type AttrValues } from "./AttributeForm";
import { ListingStatusBadge } from "./ListingStatusBadge";
import { PhotoManager } from "./PhotoManager";
import { PriceEditor } from "./PriceEditor";
import { Button } from "./ui/Button";
import { Input } from "./ui/Input";
import { Select, type Option } from "./ui/Select";
import { Skeleton } from "./ui/Skeleton";

type Listing = Schemas["OwnerListingOut"];
type Patch = Schemas["ListingPatch"];

const LocationPinMap = dynamic(() => import("./LocationPinMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full rounded-xl" />,
});


type Props = {
  initial: Listing;
  schema: Record<string, unknown>[];
  regions: Option[];
  districts: Option[];
  step: Step;
  tileUrl: string;
};

/** Step-by-step listing editor (T105). Each step saves to the API before moving on. */
export function ListingWizard({ initial, schema, regions, districts: initialDistricts, step: firstStep, tileUrl }: Props) {
  const t = useTranslations();
  const locale = useLocale() === "en" ? "en" : "sw";
  const router = useRouter();
  const [listing, setListing] = useState(initial);
  const [step, setStep] = useState<Step>(firstStep);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const live = listing.status === "active" || listing.status === "paused";
  const path = { listing_id: listing.id };

  // The form shows proposed values while a change waits for review.
  const pending = (listing.pending_changes ?? {}) as Record<string, unknown>;
  const current = <K extends keyof Listing>(key: K): Listing[K] =>
    (key in pending ? pending[key as string] : listing[key]) as Listing[K];

  const go = (next: Step) => {
    setError(null);
    setFieldErrors({});
    setStep(next);
    window.scrollTo({ top: 0 });
  };
  const nextStep = () => go(STEPS[Math.min(STEPS.indexOf(step) + 1, STEPS.length - 1)]);

  async function refresh() {
    const { data } = await api.GET("/api/v1/owner/listings/{listing_id}", { params: { path } });
    if (data) setListing(data);
  }

  async function patch(body: Patch, advance = true) {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const { data, error: err } = await api.PATCH("/api/v1/owner/listings/{listing_id}", {
        params: { path },
        body,
      });
      if (data) {
        setListing(data);
        if (advance) nextStep();
        return;
      }
      const e = apiError(err);
      if (e?.code === "INVALID_ATTRIBUTES") {
        setFieldErrors((e.details.fields ?? {}) as Record<string, string>);
      }
      setError(e?.message ?? t("errors.generic"));
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  async function action(call: "submit" | "pause" | "resume") {
    setBusy(true);
    setError(null);
    try {
      const options = { params: { path } };
      const { data, error: err } =
        call === "submit"
          ? await api.POST("/api/v1/owner/listings/{listing_id}/submit", options)
          : call === "pause"
            ? await api.POST("/api/v1/owner/listings/{listing_id}/pause", options)
            : await api.POST("/api/v1/owner/listings/{listing_id}/resume", options);
      if (data) setListing(data);
      else {
        const e = apiError(err);
        const missing = (e?.details.missing ?? []) as string[];
        setError(
          missing.length
            ? `${e?.message} ${missing.map((m) => t(`wizard.missing.${m}`)).join(", ")}`
            : (e?.message ?? t("errors.generic")),
        );
      }
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await api.DELETE("/api/v1/owner/listings/{listing_id}", {
        params: { path },
      });
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      else router.push("/owner/listings");
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const title = (locale === "en" ? listing.title_en || listing.title_sw : listing.title_sw || listing.title_en) || t("ownerListings.untitled");

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <Link href="/owner/listings" className="text-sm text-brand-700 hover:underline">
          ← {t("ownerListings.title")}
        </Link>
        <h1 className="text-xl font-bold text-ink">{title}</h1>
        <p className="text-sm text-muted">{listing.category.name}</p>
        <ListingStatusBadge listing={listing} />
        {live && listing.review_state === "pending" && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{t("wizard.liveReviewNote")}</p>
        )}
        {listing.rejection_reason && listing.status !== "active" && listing.status !== "paused" && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-danger">
            {t("wizard.rejectedBecause", { reason: listing.rejection_reason })}
          </p>
        )}
        {live && listing.review_state === "rejected" && listing.rejection_reason && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-danger">
            {t("wizard.changesRejected", { reason: listing.rejection_reason })}
          </p>
        )}
      </header>

      <nav aria-label={t("wizard.steps")} className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => go(s)}
            aria-current={step === s ? "step" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ${
              step === s ? "bg-brand-600 text-white" : "bg-canvas text-ink hover:bg-brand-50"
            }`}
          >
            {i + 1}. {t(`wizard.step.${s}`)}
          </button>
        ))}
      </nav>

      <section aria-labelledby="step-title" className="flex flex-col gap-4">
        <h2 id="step-title" className="text-base font-semibold text-ink">
          {t(`wizard.step.${step}`)}
        </h2>
        {step === "details" && (
          <DetailsStep
            key={listing.updated_at}
            listing={listing}
            current={current}
            schema={schema}
            locale={locale}
            errors={fieldErrors}
            busy={busy}
            onSave={(body) => patch(body)}
          />
        )}
        {step === "location" && (
          <LocationStep
            current={current}
            regions={regions}
            initialDistricts={initialDistricts}
            tileUrl={tileUrl}
            busy={busy}
            onSave={(body) => patch(body)}
          />
        )}
        {step === "photos" && (
          <>
            <PhotoManager listing={listing} onChanged={refresh} />
            <Button size="lg" full onClick={nextStep}>
              {t("wizard.continue")}
            </Button>
          </>
        )}
        {step === "prices" && (
          <PriceEditor
            listing={listing}
            onSaved={(saved) => {
              setListing(saved);
              nextStep();
            }}
          />
        )}
        {step === "rules" && <RulesStep listing={listing} busy={busy} onSave={(body) => patch(body)} />}
        {step === "review" && (
          <ReviewStep
            listing={listing}
            busy={busy}
            onSubmit={() => action("submit")}
            onPause={() => action("pause")}
            onResume={() => action("resume")}
            onDelete={remove}
            onFix={(m) => go(MISSING_STEP[m] ?? "details")}
          />
        )}
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}

const MISSING_STEP: Record<string, Step> = {
  title: "details",
  description: "details",
  attributes: "details",
  location: "location",
  photo: "photos",
  price: "prices",
};

type Current = <K extends keyof Listing>(key: K) => Listing[K];

function DetailsStep({
  listing,
  current,
  schema,
  locale,
  errors,
  busy,
  onSave,
}: {
  listing: Listing;
  current: Current;
  schema: Record<string, unknown>[];
  locale: "sw" | "en";
  errors: Record<string, string>;
  busy: boolean;
  onSave: (body: Patch) => void;
}) {
  const t = useTranslations("wizard");
  const [text, setText] = useState({
    title_sw: current("title_sw") ?? "",
    title_en: current("title_en") ?? "",
    description_sw: current("description_sw") ?? "",
    description_en: current("description_en") ?? "",
  });
  const [attrs, setAttrs] = useState<AttrValues>(current("attributes") ?? {});
  const bind = (key: keyof typeof text) => ({
    value: text[key],
    onChange: (e: { target: { value: string } }) => setText((v) => ({ ...v, [key]: e.target.value })),
  });

  function save(e: FormEvent) {
    e.preventDefault();
    const nullable = (v: string) => v.trim() || null;
    onSave({
      title_sw: nullable(text.title_sw),
      title_en: nullable(text.title_en),
      description_sw: nullable(text.description_sw),
      description_en: nullable(text.description_en),
      attributes: attrs,
    });
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t("bilingualHint")}</p>
      <Input label={t("titleSw")} maxLength={120} {...bind("title_sw")} />
      <Input label={t("titleEn")} maxLength={120} {...bind("title_en")} />
      <TextArea label={t("descriptionSw")} {...bind("description_sw")} />
      <TextArea label={t("descriptionEn")} {...bind("description_en")} />
      {schema.length > 0 && (
        <>
          <h3 className="pt-2 text-base font-semibold text-ink">{t("features", { category: listing.category.name })}</h3>
          <AttributeForm schema={schema} values={attrs} onChange={setAttrs} errors={errors} locale={locale} />
        </>
      )}
      <Button type="submit" size="lg" full loading={busy}>
        {t("saveContinue")}
      </Button>
    </form>
  );
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (e: { target: { value: string } }) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium text-ink">{label}</span>
      <textarea
        rows={5}
        maxLength={5000}
        value={value}
        onChange={onChange}
        className="rounded-lg border border-line bg-surface p-3 text-base text-ink"
      />
    </label>
  );
}

function LocationStep({
  current,
  regions,
  initialDistricts,
  tileUrl,
  busy,
  onSave,
}: {
  current: Current;
  regions: Option[];
  initialDistricts: Option[];
  tileUrl: string;
  busy: boolean;
  onSave: (body: Patch) => void;
}) {
  const t = useTranslations();
  const [region, setRegion] = useState(String(current("region_id") ?? ""));
  const [district, setDistrict] = useState(String(current("district_id") ?? ""));
  const [districts, setDistricts] = useState(initialDistricts);
  const [hint, setHint] = useState(current("address_hint") ?? "");
  const lat = current("lat");
  const lng = current("lng");
  const [pin, setPin] = useState(lat != null && lng != null ? { lat, lng } : null);

  const initialRegion = String(current("region_id") ?? "");
  useEffect(() => {
    if (!region) {
      setDistricts([]);
      return;
    }
    if (region === initialRegion && initialDistricts.length) {
      setDistricts(initialDistricts);
      return;
    }
    let cancelled = false;
    api
      .GET("/api/v1/locations", { params: { query: { parent_id: Number(region) } } })
      .then(({ data }) => {
        if (!cancelled && data) {
          setDistricts(data.map((d) => ({ value: String(d.id), label: d.name })));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [region, initialRegion, initialDistricts]);

  function save(e: FormEvent) {
    e.preventDefault();
    onSave({
      region_id: Number(region),
      district_id: Number(district),
      address_hint: hint.trim() || null,
      lat: pin?.lat ?? null,
      lng: pin?.lng ?? null,
    });
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      <Select
        label={t("filters.region")}
        placeholder=""
        required
        value={region}
        onChange={(e) => {
          setRegion(e.target.value);
          setDistrict("");
        }}
        options={regions}
      />
      <Select
        label={t("filters.district")}
        placeholder=""
        required
        value={district}
        onChange={(e) => setDistrict(e.target.value)}
        options={districts}
      />
      <Input
        label={t("wizard.addressHint")}
        hint={t("wizard.addressHintHelp")}
        maxLength={300}
        value={hint}
        onChange={(e) => setHint(e.target.value)}
      />
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">{t("wizard.pin")}</span>
        <p className="text-sm text-muted">{t("wizard.pinHint")}</p>
        <LocationPinMap value={pin} onChange={setPin} tileUrl={tileUrl} attribution={t("map.attribution")} />
        {pin && (
          <Button variant="ghost" onClick={() => setPin(null)}>
            {t("wizard.clearPin")}
          </Button>
        )}
      </div>
      <Button type="submit" size="lg" full loading={busy}>
        {t("wizard.saveContinue")}
      </Button>
    </form>
  );
}

function RulesStep({ listing, busy, onSave }: { listing: Listing; busy: boolean; onSave: (body: Patch) => void }) {
  const t = useTranslations();
  const mode = listing.category.booking_mode;
  const slot = (listing.slot_config ?? {}) as { open?: string; close?: string; slot_minutes?: number };
  const [policy, setPolicy] = useState(listing.cancellation_policy);
  const [instant, setInstant] = useState(listing.instant_book);
  const [minD, setMinD] = useState(String(listing.min_duration ?? ""));
  const [maxD, setMaxD] = useState(String(listing.max_duration ?? ""));
  const [stock, setStock] = useState(String(listing.stock));
  const [open, setOpen] = useState(slot.open ?? "08:00");
  const [close, setClose] = useState(slot.close ?? "22:00");
  const [minutes, setMinutes] = useState(String(slot.slot_minutes ?? 60));
  const unit = t(`units.${listing.category.default_unit}`);

  function save(e: FormEvent) {
    e.preventDefault();
    const num = (v: string) => (v ? Number(v) : null);
    const body: Patch = {
      cancellation_policy: policy,
      instant_book: mode === "LEASE" ? false : instant,
      min_duration: num(minD),
      max_duration: num(maxD),
    };
    if (mode === "QUANTITY") body.stock = Number(stock) || 1;
    if (mode === "TIME_SLOT") body.slot_config = { ...slot, open, close, slot_minutes: Number(minutes) };
    onSave(body);
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4">
      <Select
        label={t("wizard.policy")}
        value={policy}
        onChange={(e) => setPolicy(e.target.value as Listing["cancellation_policy"])}
        options={(["flexible", "moderate", "strict"] as const).map((p) => ({
          value: p,
          label: `${t(`policy.${p}`)}: ${t(`wizard.policyHint.${p}`)}`,
        }))}
      />
      {mode !== "LEASE" ? (
        <label className="flex items-start gap-3 text-sm text-ink">
          <input
            type="checkbox"
            className="mt-0.5 size-5 accent-brand-600"
            checked={instant}
            onChange={(e) => setInstant(e.target.checked)}
          />
          <span>
            <span className="font-medium">{t("wizard.instantBook")}</span>
            <span className="block text-muted">{t("wizard.instantBookHint")}</span>
          </span>
        </label>
      ) : (
        <p className="text-sm text-muted">{t("wizard.leaseApproval")}</p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Input label={t("wizard.minDuration", { unit })} type="number" inputMode="numeric" min={1} value={minD} onChange={(e) => setMinD(e.target.value)} />
        <Input label={t("wizard.maxDuration", { unit })} type="number" inputMode="numeric" min={1} value={maxD} onChange={(e) => setMaxD(e.target.value)} />
      </div>
      {mode === "QUANTITY" && (
        <Input label={t("wizard.stock")} hint={t("wizard.stockHint")} type="number" inputMode="numeric" min={1} required value={stock} onChange={(e) => setStock(e.target.value)} />
      )}
      {mode === "TIME_SLOT" && (
        <div className="grid grid-cols-2 gap-2">
          <Input label={t("wizard.opens")} type="time" value={open} onChange={(e) => setOpen(e.target.value)} />
          <Input label={t("wizard.closes")} type="time" value={close} onChange={(e) => setClose(e.target.value)} />
          <div className="col-span-2">
            <Select
              label={t("wizard.slotLength")}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              options={[30, 60, 120].map((m) => ({ value: String(m), label: t("wizard.minutes", { count: m }) }))}
            />
          </div>
        </div>
      )}
      <Button type="submit" size="lg" full loading={busy}>
        {t("wizard.saveContinue")}
      </Button>
    </form>
  );
}

function ReviewStep({
  listing,
  busy,
  onSubmit,
  onPause,
  onResume,
  onDelete,
  onFix,
}: {
  listing: Listing;
  busy: boolean;
  onSubmit: () => void;
  onPause: () => void;
  onResume: () => void;
  onDelete: () => void;
  onFix: (missing: string) => void;
}) {
  const t = useTranslations("wizard");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const canSubmit = listing.status === "draft" || listing.status === "rejected";
  const note: Record<string, ReactNode> = {
    pending_review: t("statusNote.pending_review"),
    active: t("statusNote.active"),
    paused: t("statusNote.paused"),
    suspended: t("statusNote.suspended"),
  };

  return (
    <div className="flex flex-col gap-4">
      {listing.missing.length > 0 ? (
        <div className="flex flex-col gap-2 rounded-xl border border-line p-4">
          <p className="text-sm font-medium text-ink">{t("missingTitle")}</p>
          <ul className="flex flex-col gap-1">
            {listing.missing.map((m) => (
              <li key={m}>
                <button type="button" onClick={() => onFix(m)} className="text-sm text-brand-700 hover:underline">
                  {t(`missing.${m}`)} →
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        canSubmit && <p className="rounded-xl bg-brand-50 p-4 text-sm text-brand-800">{t("ready")}</p>
      )}
      {note[listing.status] && <p className="text-sm text-muted">{note[listing.status]}</p>}
      {canSubmit && (
        <Button size="lg" full loading={busy} disabled={listing.missing.length > 0} onClick={onSubmit}>
          {t("submit")}
        </Button>
      )}
      {listing.status === "active" && (
        <Button variant="secondary" full loading={busy} onClick={onPause}>
          {t("pause")}
        </Button>
      )}
      {listing.status === "paused" && (
        <Button full loading={busy} onClick={onResume}>
          {t("resume")}
        </Button>
      )}
      {confirmDelete ? (
        <div className="flex flex-col gap-2 rounded-xl border border-red-200 p-4">
          <p className="text-sm text-ink">{t("deleteConfirm")}</p>
          <div className="flex gap-2">
            <Button variant="danger" loading={busy} onClick={onDelete}>
              {t("delete")}
            </Button>
            <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
              {t("keep")}
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="ghost" className="text-danger" onClick={() => setConfirmDelete(true)}>
          {t("delete")}
        </Button>
      )}
    </div>
  );
}
