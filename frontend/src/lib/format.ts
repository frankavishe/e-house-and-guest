// Formatting helpers (research.md R13). Money is integer TZS; instants are shown in EAT.

export const EAT = "Africa/Dar_es_Salaam";

type Locale = "sw" | "en";

const groupFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** `1250000` → `TSh 1,250,000` (no decimals, same grouping in both languages). */
export function formatTZS(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  return `${sign}TSh ${groupFormat.format(Math.abs(Math.round(amount)))}`;
}

const dateLocale: Record<Locale, string> = { sw: "sw-TZ", en: "en-GB" };

function toDate(value: string | Date): Date {
  return typeof value === "string" ? new Date(value) : value;
}

/** `2026-11-02T06:00:00Z` → `2 Nov 2026` (en) / `2 Nov 2026` style in Swahili, in EAT. */
export function formatDate(value: string | Date, locale: Locale): string {
  return new Intl.DateTimeFormat(dateLocale[locale], {
    timeZone: EAT,
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(toDate(value));
}

/** 24-hour EAT time, e.g. `09:00`. */
export function formatTime(value: string | Date, locale: Locale): string {
  return new Intl.DateTimeFormat(dateLocale[locale], {
    timeZone: EAT,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(toDate(value));
}

export function formatDateTime(value: string | Date, locale: Locale): string {
  return `${formatDate(value, locale)}, ${formatTime(value, locale)}`;
}

/** Calendar date (YYYY-MM-DD) of an instant in EAT. */
export function eatDateString(value: string | Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: EAT,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(toDate(value));
  return parts; // en-CA formats as YYYY-MM-DD
}

export type Localized = { sw?: string | null; en?: string | null };

/** Pick the requested language, falling back to the other one (listing titles, labels). */
export function localized(value: Localized | null | undefined, locale: Locale): string {
  if (!value) return "";
  const other: Locale = locale === "sw" ? "en" : "sw";
  return value[locale] || value[other] || "";
}

/** Display form of an E.164 Tanzanian number: `+255712345678` → `0712 345 678`. */
export function formatPhone(e164: string): string {
  const m = /^\+255(\d{3})(\d{3})(\d{3})$/.exec(e164);
  return m ? `0${m[1]} ${m[2]} ${m[3]}` : e164;
}
