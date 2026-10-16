"use client";

import { useState } from "react";

type Props = {
  src: string | null | undefined;
  /** Optional responsive sources, e.g. `url_320 320w, url_640 640w`. */
  srcSet?: string;
  sizes?: string;
  alt: string;
  fallbackLabel: string;
  /** CSS aspect ratio of the frame, e.g. "4 / 3". The frame size never depends on the image. */
  aspect?: string;
  className?: string;
  priority?: boolean;
};

/**
 * An image in a fixed-ratio frame. If the image is missing or fails to load, the frame
 * stays the same size and shows a neutral placeholder (Principle VI).
 */
export function ImageWithFallback({
  src,
  srcSet,
  sizes,
  alt,
  fallbackLabel,
  aspect = "4 / 3",
  className = "",
  priority = false,
}: Props) {
  const [failed, setFailed] = useState(false);
  const showImage = Boolean(src) && !failed;
  return (
    <div
      className={`relative overflow-hidden bg-line ${className}`}
      style={{ aspectRatio: aspect }}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- plain img: srcset from our own variants
        <img
          src={src ?? undefined}
          srcSet={srcSet}
          sizes={sizes}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          fetchPriority={priority ? "high" : undefined}
          onError={() => setFailed(true)}
          className="absolute inset-0 size-full object-cover"
        />
      ) : (
        <div
          role="img"
          aria-label={alt || fallbackLabel}
          className="absolute inset-0 flex items-center justify-center text-xs text-muted"
        >
          <svg aria-hidden viewBox="0 0 24 24" className="mr-1 size-5 fill-none stroke-current">
            <rect x="3" y="5" width="18" height="14" rx="2" strokeWidth="1.5" />
            <path d="m3 16 5-5 4 4 3-3 6 6" strokeWidth="1.5" />
          </svg>
          {fallbackLabel}
        </div>
      )}
    </div>
  );
}
