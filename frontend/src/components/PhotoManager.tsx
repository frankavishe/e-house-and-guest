"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, apiError, type Schemas } from "@/lib/api/client";
import { uploadFile } from "@/lib/upload";
import { ImageWithFallback } from "./ImageWithFallback";
import { Badge } from "./ui/Badge";
import { Button, buttonClasses } from "./ui/Button";

type Listing = Schemas["OwnerListingOut"];

const ACCEPT = "image/jpeg,image/png,image/webp";

/** Upload (presigned PUT, then confirm), remove and order photos. On a live listing new
 * photos show "in review" until an admin approves them. */
export function PhotoManager({
  listing,
  onChanged,
}: {
  listing: Listing;
  onChanged: () => Promise<void>;
}) {
  const t = useTranslations();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { listing_id: listing.id };

  async function add(files: FileList) {
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        let photoId = "";
        const key = await uploadFile(async () => {
          const { data, error: err } = await api.POST("/api/v1/owner/listings/{listing_id}/photos", {
            params: { path },
            body: { content_type: file.type },
          });
          if (err) setError(apiError(err)?.message ?? t("errors.generic"));
          photoId = data?.photo_id ?? "";
          return data;
        }, file);
        if (!key) {
          setError((e) => e ?? t("wizard.uploadFailed"));
          break;
        }
        const { error: err } = await api.PATCH(
          "/api/v1/owner/listings/{listing_id}/photos/{photo_id}",
          { params: { path: { ...path, photo_id: photoId } }, body: { confirmed: true } },
        );
        if (err) {
          setError(apiError(err)?.message ?? t("errors.generic"));
          break;
        }
      }
      await onChanged();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  async function run(call: () => Promise<{ error?: unknown }>) {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await call();
      if (err) setError(apiError(err)?.message ?? t("errors.generic"));
      await onChanged();
    } catch {
      setError(t("errors.network"));
    } finally {
      setBusy(false);
    }
  }

  const remove = (photoId: string) =>
    run(() =>
      api.DELETE("/api/v1/owner/listings/{listing_id}/photos/{photo_id}", {
        params: { path: { ...path, photo_id: photoId } },
      }),
    );

  // Re-number every photo so the chosen one comes first.
  const makeCover = (photoId: string) =>
    run(async () => {
      const order = [photoId, ...listing.photos.map((p) => p.id).filter((id) => id !== photoId)];
      for (const [position, id] of order.entries()) {
        const res = await api.PATCH("/api/v1/owner/listings/{listing_id}/photos/{photo_id}", {
          params: { path: { ...path, photo_id: id } },
          body: { position },
        });
        if (res.error) return res;
      }
      return {};
    });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">{t("wizard.photosHint")}</p>
      {listing.photos.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {listing.photos.map((photo, i) => (
            <li key={photo.id} className="flex flex-col gap-1">
              <ImageWithFallback
                src={photo.url_320}
                alt={photo.alt_sw ?? photo.alt_en ?? ""}
                fallbackLabel={t("common.imageUnavailable")}
                className="aspect-[4/3] w-full rounded-lg"
              />
              <div className="flex flex-wrap items-center gap-1">
                {i === 0 && <Badge tone="brand">{t("wizard.cover")}</Badge>}
                {photo.pending && <Badge tone="warning">{t("wizard.inReview")}</Badge>}
              </div>
              <div className="flex gap-1">
                {i > 0 && (
                  <Button variant="ghost" className="h-8 px-2" disabled={busy} onClick={() => makeCover(photo.id)}>
                    {t("wizard.makeCover")}
                  </Button>
                )}
                <Button variant="ghost" className="h-8 px-2 text-danger" disabled={busy} onClick={() => remove(photo.id)}>
                  {t("wizard.remove")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <label className={`${buttonClasses("secondary", "lg", true)} cursor-pointer`} aria-busy={busy || undefined}>
        {busy ? t("common.loading") : t("wizard.addPhotos")}
        <input
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          disabled={busy}
          data-testid="photo-input"
          onChange={(e) => {
            if (e.target.files?.length) add(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
