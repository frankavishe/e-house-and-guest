"use client";

import { useState } from "react";
import { buttonClasses } from "./ui/Button";

/** WhatsApp share (the common way listings travel in Tanzania), plus native share or copy. */
export function ShareLinks({
  url,
  title,
  labels,
}: {
  url: string;
  title: string;
  labels: { whatsapp: string; share: string; copied: string };
}) {
  const [copied, setCopied] = useState(false);
  const whatsapp = `https://wa.me/?text=${encodeURIComponent(`${title} ${url}`)}`;

  async function share() {
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Cancelled or blocked: nothing to do.
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <a
        href={whatsapp}
        target="_blank"
        rel="noopener noreferrer"
        className={buttonClasses("secondary")}
      >
        {labels.whatsapp}
      </a>
      <button type="button" onClick={share} className={buttonClasses("ghost")}>
        {copied ? labels.copied : labels.share}
      </button>
    </div>
  );
}
